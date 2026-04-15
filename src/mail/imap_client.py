from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email import message_from_bytes
from email.message import Message
from email.utils import parsedate_to_datetime, parseaddr
import imaplib
from typing import Iterable

from mail.models import IncomingEmail


@dataclass(slots=True)
class IMAPClient:
    host: str
    port: int = 993
    username: str | None = None
    password: str | None = None
    mailbox: str = "INBOX"
    use_ssl: bool = True

    def fetch_unread_messages(self) -> list[tuple[bytes, IncomingEmail]]:
        """
        Fetch unread IMAP messages and return:
            [(imap_message_id, IncomingEmail), ...]
        """
        messages: list[tuple[bytes, IncomingEmail]] = []

        with self._connect() as client:
            self._select_mailbox(client)

            typ, data = client.search(None, "UNSEEN")
            if typ != "OK":
                raise RuntimeError(f"IMAP search failed: {typ}")

            raw_ids = data[0].split() if data and data[0] else []
            for imap_message_id in raw_ids:
                typ, msg_data = client.fetch(imap_message_id, "(RFC822)")
                if typ != "OK":
                    continue

                raw_bytes = self._extract_rfc822_bytes(msg_data)
                if not raw_bytes:
                    continue

                email_message = message_from_bytes(raw_bytes)
                incoming = self._to_incoming_email(email_message, imap_message_id)
                messages.append((imap_message_id, incoming))

        return messages

    def mark_seen(self, imap_message_id: bytes) -> None:
        with self._connect() as client:
            self._select_mailbox(client)
            typ, _ = client.store(imap_message_id, "+FLAGS", "\\Seen")
            if typ != "OK":
                raise RuntimeError(f"Failed to mark message as seen: {imap_message_id!r}")

    def mark_unseen(self, imap_message_id: bytes) -> None:
        with self._connect() as client:
            self._select_mailbox(client)
            typ, _ = client.store(imap_message_id, "-FLAGS", "\\Seen")
            if typ != "OK":
                raise RuntimeError(f"Failed to mark message as unseen: {imap_message_id!r}")

    def _connect(self) -> imaplib.IMAP4:
        if self.use_ssl:
            client = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            client = imaplib.IMAP4(self.host, self.port)

        if self.username:
            client.login(self.username, self.password or "")

        return client

    def _select_mailbox(self, client: imaplib.IMAP4) -> None:
        typ, _ = client.select(self.mailbox)
        if typ != "OK":
            raise RuntimeError(f"Unable to select mailbox: {self.mailbox}")

    def _extract_rfc822_bytes(self, msg_data: Iterable[object]) -> bytes | None:
        for item in msg_data:
            if isinstance(item, tuple) and len(item) >= 2:
                payload = item[1]
                if isinstance(payload, bytes):
                    return payload
        return None

    def _to_incoming_email(self, msg: Message, imap_message_id: bytes) -> IncomingEmail:
        raw_from = msg.get("From", "")
        _, sender_email = parseaddr(raw_from)

        subject = self._decode_header_value(msg.get("Subject"))
        text_body = self._extract_text_body(msg)
        message_id = self._resolve_message_id(msg, sender_email, subject, imap_message_id)
        received_at = self._extract_received_at(msg)

        in_reply_to = self._extract_single_message_id(msg.get("In-Reply-To"))
        references = self._extract_message_id_list(msg.get("References"))

        metadata = {
            "imap_message_id": imap_message_id.decode("utf-8", errors="replace"),
            "raw_from": raw_from,
            "to": self._decode_header_value(msg.get("To")),
            "date_header": msg.get("Date", ""),
        }

        return IncomingEmail(
            message_id=message_id,
            sender=sender_email.strip(),
            subject=subject,
            text_body=text_body,
            received_at=received_at,
            metadata=metadata,
            in_reply_to=in_reply_to,
            references=references,
        )

    def _resolve_message_id(
        self,
        msg: Message,
        sender_email: str,
        subject: str,
        imap_message_id: bytes,
    ) -> str:
        raw_message_id = (msg.get("Message-ID") or "").strip()
        if raw_message_id:
            return raw_message_id

        sender = (sender_email or "").strip().lower() or "unknown"
        clean_subject = (subject or "").strip() or "(no-subject)"
        imap_id = imap_message_id.decode("utf-8", errors="replace")
        return f"fallback:{sender}:{clean_subject}:{imap_id}"

    def _extract_received_at(self, msg: Message) -> datetime:
        raw_date = (msg.get("Date") or "").strip()
        if raw_date:
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass

        return datetime.now(timezone.utc)

    def _extract_text_body(self, msg: Message) -> str:
        if msg.is_multipart():
            plain_parts: list[str] = []

            for part in msg.walk():
                content_disposition = (part.get("Content-Disposition") or "").lower()
                content_type = (part.get_content_type() or "").lower()

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    text = self._decode_part_payload(part)
                    if text.strip():
                        plain_parts.append(text.strip())

            if plain_parts:
                return "\n\n".join(plain_parts).strip()

            for part in msg.walk():
                content_disposition = (part.get("Content-Disposition") or "").lower()
                content_type = (part.get_content_type() or "").lower()

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/html":
                    html = self._decode_part_payload(part)
                    if html.strip():
                        return self._html_to_text(html)

            return ""

        content_type = (msg.get_content_type() or "").lower()
        text = self._decode_part_payload(msg)

        if content_type == "text/html":
            return self._html_to_text(text)

        return text.strip()

    def _decode_part_payload(self, part: Message) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            return raw.strip() if isinstance(raw, str) else ""

        charset = part.get_content_charset() or "utf-8"

        try:
            return payload.decode(charset, errors="replace").strip()
        except LookupError:
            return payload.decode("utf-8", errors="replace").strip()

    def _decode_header_value(self, value: str | None) -> str:
        if not value:
            return ""

        try:
            from email.header import decode_header

            parts = decode_header(value)
            decoded: list[str] = []

            for chunk, encoding in parts:
                if isinstance(chunk, bytes):
                    enc = encoding or "utf-8"
                    try:
                        decoded.append(chunk.decode(enc, errors="replace"))
                    except LookupError:
                        decoded.append(chunk.decode("utf-8", errors="replace"))
                else:
                    decoded.append(chunk)

            return "".join(decoded).strip()
        except Exception:
            return value.strip()

    def _unfold_header_value(self, raw_value: str | None) -> str:
        if not raw_value:
            return ""

        return " ".join(str(raw_value).replace("\r", " ").replace("\n", " ").split()).strip()

    def _extract_single_message_id(self, raw_value: str | None) -> str | None:
        text = self._unfold_header_value(raw_value)
        if not text:
            return None

        parts = text.split()
        return parts[0] if parts else None

    def _extract_message_id_list(self, raw_value: str | None) -> list[str]:
        if not raw_value:
            return []

        import re

        text = self._unfold_header_value(raw_value)
        if not text:
            return []

        parts = [part.strip() for part in re.split(r"[\s,]+", text) if part.strip()]

        out: list[str] = []
        seen: set[str] = set()

        for part in parts:
            if part in seen:
                continue
            seen.add(part)
            out.append(part)

        return out

    def _html_to_text(self, html: str) -> str:
        """
        Small dependency-free HTML-to-text fallback for version 1.
        """
        import re

        text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", "", html)
        text = re.sub(r"(?i)<br\\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\\s*>", "\n\n", text)
        text = re.sub(r"(?s)<.*?>", "", text)

        text = (
            text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
        )

        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
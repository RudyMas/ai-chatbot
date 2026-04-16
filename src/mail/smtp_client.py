from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
import smtplib
from typing import Optional


@dataclass(slots=True)
class SMTPClient:
    host: str | None
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str | None = None
    from_name: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_email)

    def send_plain_text(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[list[str]] = None,
    ) -> tuple[bool, bytes | None]:
        if not self.enabled:
            return False, None

        try:
            message = self.build_plain_text_message(
                to_email=to_email,
                subject=subject,
                body=body,
                reply_to=reply_to,
                message_id=message_id,
                in_reply_to=in_reply_to,
                references=references,
            )
            raw_message = message.as_bytes(policy=SMTP)

            if self.use_ssl:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=20)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=20)

            with smtp:
                smtp.ehlo()

                if self.use_tls and not self.use_ssl:
                    smtp.starttls()
                    smtp.ehlo()

                if self.username:
                    smtp.login(self.username, self.password or "")

                smtp.send_message(message)

            return True, raw_message

        except Exception as exc:
            print(f"[SMTP ERROR] Failed to send email to {to_email}: {exc}")
            return False, None

    def build_plain_text_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[list[str]] = None,
    ) -> EmailMessage:
        clean_body = (body or "").strip()
        if not clean_body:
            clean_body = "(empty response)"

        message = EmailMessage()

        clean_from_email = self._clean_header_value(self.from_email) or ""
        clean_from_name = self._clean_header_value(self.from_name)

        if clean_from_name:
            message["From"] = formataddr((clean_from_name, clean_from_email))
        else:
            message["From"] = clean_from_email

        message["To"] = self._clean_header_value(to_email) or ""
        message["Subject"] = self._clean_header_value(subject) or "(no subject)"

        clean_message_id = self._clean_single_header_token(message_id)
        if clean_message_id:
            message["Message-ID"] = clean_message_id

        clean_in_reply_to = self._clean_single_header_token(in_reply_to)
        if clean_in_reply_to:
            message["In-Reply-To"] = clean_in_reply_to

        clean_refs = self._clean_header_tokens(references)
        if clean_refs:
            message["References"] = " ".join(clean_refs)

        clean_reply_to = self._clean_header_value(reply_to)
        if clean_reply_to:
            message["Reply-To"] = clean_reply_to

        message.set_content(clean_body)
        return message

    def _clean_header_value(self, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = " ".join(str(value).replace("\r", " ").replace("\n", " ").split()).strip()
        return cleaned or None

    def _clean_single_header_token(self, value: str | None) -> str | None:
        cleaned = self._clean_header_value(value)
        if not cleaned:
            return None

        return cleaned.split()[0]

    def _clean_header_tokens(self, values: Optional[list[str]]) -> list[str]:
        if not values:
            return []

        out: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = self._clean_single_header_token(value)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            out.append(cleaned)

        return out
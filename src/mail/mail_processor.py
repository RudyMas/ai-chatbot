from __future__ import annotations

from typing import Any
import uuid

from mail.chat_client import ChatClient
from mail.config import MailConfig
from mail.contacts import ContactManager
from mail.models import IncomingEmail, MailAction, ProcessingResult
from mail.smtp_client import SMTPClient
from mail.storage import (
    ProcessedMessageStore,
    append_jsonl,
    normalize_email,
    read_jsonl,
    utc_now_iso,
)
from mail.templates import onboarding_body, onboarding_subject, pending_approval_body
from mail.mail_threading import (
    canonicalize_subject,
    normalize_message_id,
    normalize_references,
    resolve_thread_id,
)


def build_reply_subject(subject: str | None, fallback_name: str) -> str:
    fallback = f"Reply from {fallback_name}".strip()

    if not subject:
        return fallback

    clean = subject.strip()
    if not clean:
        return fallback

    if clean.lower().startswith("re:"):
        return clean

    return f"Re: {clean}"


class MailProcessor:
    def __init__(
        self,
        config: MailConfig,
        contact_manager: ContactManager,
        processed_storage: ProcessedMessageStore,
        chat_client: ChatClient,
        smtp_client: SMTPClient,
    ):
        self.config = config
        self.contact_manager = contact_manager
        self.processed_storage = processed_storage
        self.chat_client = chat_client
        self.smtp_client = smtp_client

    def process_message(self, message: IncomingEmail) -> ProcessingResult:
        sender = normalize_email(message.sender)
        message_id = self._resolve_message_id(message, sender)
        assistant_name = self.config.smtp.from_name or self.config.behavior.chat_user
        signature = self.config.behavior.signature

        try:
            if self.processed_storage.has_message(message_id):
                return ProcessingResult(
                    sender=sender,
                    action=MailAction.ALREADY_PROCESSED,
                    email_sent=False,
                    details={"message_id": message_id},
                )

            thread_id = self._resolve_incoming_thread_id(message, sender, message_id)
            self._log_inbound(message, thread_id=thread_id, resolved_message_id=message_id)

            if self.contact_manager.is_blacklisted(sender):
                self.processed_storage.add(
                    message_id,
                    sender,
                    MailAction.IGNORED_BLACKLIST,
                    details={
                        "message_id": message_id,
                        "thread_id": thread_id,
                        "incoming_in_reply_to": message.in_reply_to,
                        "incoming_references": message.references,
                    },
                )
                return ProcessingResult(
                    sender=sender,
                    action=MailAction.IGNORED_BLACKLIST,
                    email_sent=False,
                    details={"message_id": message_id, "thread_id": thread_id},
                )

            if self.contact_manager.is_whitelisted(sender):
                contact_note = self.contact_manager.get_contact_note(sender, "whitelist")
                thread_context = self._build_thread_context(thread_id=thread_id)
                is_followup = bool(message.in_reply_to or message.references or thread_context)

                reply_text = self.chat_client.build_reply(
                    sender=sender,
                    subject=message.subject,
                    body=message.text_body,
                    contact_note=contact_note,
                    thread_context=thread_context,
                    is_followup=is_followup,
                )

                reply_subject = build_reply_subject(message.subject, assistant_name)
                outbound_message_id = self._build_outbound_message_id()

                thread_references = list(message.references or [])
                if message.message_id and message.message_id not in thread_references:
                    thread_references.append(message.message_id)

                sent = self.smtp_client.send_plain_text(
                    to_email=sender,
                    subject=reply_subject,
                    body=reply_text,
                    message_id=outbound_message_id,
                    in_reply_to=message.message_id,
                    references=thread_references,
                )

                details = {
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "smtp_enabled": self.smtp_client.enabled,
                    "reply_subject": reply_subject,
                    "outbound_message_id": outbound_message_id,
                    "in_reply_to": message.message_id,
                    "references": thread_references,
                    "incoming_in_reply_to": message.in_reply_to,
                    "incoming_references": message.references,
                    "thread_context_used": bool(thread_context),
                    "is_followup": is_followup,
                }

                self._log_outbound(
                    sender=sender,
                    subject=reply_subject,
                    body=reply_text,
                    kind="whitelist_reply",
                    sent=sent,
                    thread_id=thread_id,
                    message_id=outbound_message_id,
                    in_reply_to=message.message_id,
                    references=thread_references,
                )
                self.processed_storage.add(
                    message_id,
                    sender,
                    MailAction.REPLIED_WHITELIST,
                    details=details,
                )

                return ProcessingResult(
                    sender=sender,
                    action=MailAction.REPLIED_WHITELIST,
                    email_sent=sent,
                    details=details,
                )

            if self.contact_manager.is_new(sender):
                return self._handle_existing_new_sender(
                    sender=sender,
                    message_id=message_id,
                    assistant_name=assistant_name,
                    signature=signature,
                    incoming_message=message,
                    thread_id=thread_id,
                )

            new_entry = self.contact_manager.add_new(sender, note="auto-added from inbound email")
            subject = onboarding_subject(self.config.behavior.onboarding_subject)
            body = onboarding_body(sender, assistant_name, signature)

            sent = self.smtp_client.send_plain_text(
                to_email=sender,
                subject=subject,
                body=body,
            )

            self._log_outbound(
                sender=sender,
                subject=subject,
                body=body,
                kind="onboarding",
                sent=sent,
                thread_id=thread_id,
            )

            if sent:
                self.contact_manager.mark_onboarding_sent(sender)

            self.processed_storage.add(
                message_id,
                sender,
                MailAction.ADDED_TO_NEW,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "onboarding_sent": sent,
                    "smtp_enabled": self.smtp_client.enabled,
                    "added_to": "new",
                    "created_at": new_entry.created_at,
                    "incoming_in_reply_to": message.in_reply_to,
                    "incoming_references": message.references,
                },
            )

            return ProcessingResult(
                sender=sender,
                action=MailAction.ADDED_TO_NEW,
                email_sent=sent,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "added_to": "new",
                    "created_at": new_entry.created_at,
                },
            )

        except Exception as exc:
            details = {
                "error": str(exc),
                "message_id": message_id,
                "incoming_in_reply_to": message.in_reply_to,
                "incoming_references": message.references,
            }
            self.processed_storage.add(message_id, sender, MailAction.ERROR, details=details)
            return ProcessingResult(
                sender=sender,
                action=MailAction.ERROR,
                email_sent=False,
                details=details,
            )

    def _handle_existing_new_sender(
        self,
        sender: str,
        message_id: str,
        assistant_name: str,
        signature: str | None,
        incoming_message: IncomingEmail,
        thread_id: str,
    ) -> ProcessingResult:
        if not self.config.behavior.send_pending_reply:
            self.processed_storage.add(
                message_id,
                sender,
                MailAction.ALREADY_NEW,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "reason": "sender already queued for review",
                    "pending_reply_enabled": False,
                    "incoming_in_reply_to": incoming_message.in_reply_to,
                    "incoming_references": incoming_message.references,
                },
            )
            return ProcessingResult(
                sender=sender,
                action=MailAction.ALREADY_NEW,
                email_sent=False,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "reason": "sender already queued for review",
                    "pending_reply_enabled": False,
                },
            )

        cooldown_hours = self.config.behavior.pending_reply_cooldown_hours
        should_send = self.contact_manager.should_send_pending_reply(sender, cooldown_hours)

        if not should_send:
            self.processed_storage.add(
                message_id,
                sender,
                MailAction.ALREADY_NEW,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "reason": "pending approval reply cooldown active",
                    "cooldown_hours": cooldown_hours,
                    "incoming_in_reply_to": incoming_message.in_reply_to,
                    "incoming_references": incoming_message.references,
                },
            )
            return ProcessingResult(
                sender=sender,
                action=MailAction.ALREADY_NEW,
                email_sent=False,
                details={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "reason": "pending approval reply cooldown active",
                    "cooldown_hours": cooldown_hours,
                },
            )

        subject = onboarding_subject(self.config.behavior.onboarding_subject)
        body = pending_approval_body(sender, assistant_name, signature)

        sent = self.smtp_client.send_plain_text(
            to_email=sender,
            subject=subject,
            body=body,
        )

        self._log_outbound(
            sender=sender,
            subject=subject,
            body=body,
            kind="pending_approval",
            sent=sent,
            thread_id=thread_id,
        )

        if sent:
            self.contact_manager.mark_pending_reply_sent(sender)

        self.processed_storage.add(
            message_id,
            sender,
            MailAction.PENDING_REPLY_SENT,
            details={
                "message_id": message_id,
                "thread_id": thread_id,
                "pending_reply_sent": sent,
                "smtp_enabled": self.smtp_client.enabled,
                "cooldown_hours": cooldown_hours,
                "incoming_in_reply_to": incoming_message.in_reply_to,
                "incoming_references": incoming_message.references,
            },
        )

        return ProcessingResult(
            sender=sender,
            action=MailAction.PENDING_REPLY_SENT,
            email_sent=sent,
            details={
                "message_id": message_id,
                "thread_id": thread_id,
                "cooldown_hours": cooldown_hours,
            },
        )

    def _resolve_message_id(self, message: IncomingEmail, sender: str) -> str:
        raw = normalize_message_id(message.message_id)
        if raw:
            return raw

        subject = self._canonical_subject(message.subject)
        return f"fallback:{sender}:{subject}:{utc_now_iso()}".lower()

    def _build_outbound_message_id(self) -> str:
        domain = (self.config.smtp.from_email or "localhost").split("@")[-1].strip() or "localhost"
        return f"<{uuid.uuid4().hex}@{domain}>"

    def _canonical_subject(self, subject: str | None) -> str:
        return canonicalize_subject(subject)

    def _resolve_incoming_thread_id(
        self,
        message: IncomingEmail,
        sender: str,
        resolved_message_id: str,
    ) -> str:
        inbound_rows = read_jsonl(self.config.paths.inbound_log)
        outbound_rows = read_jsonl(self.config.paths.outbound_log)

        timestamp = message.received_at.isoformat(timespec="seconds")

        return resolve_thread_id(
            profile_name=self.config.profile_name,
            sender_email=sender,
            subject=message.subject,
            timestamp=timestamp,
            message_id=resolved_message_id,
            in_reply_to=message.in_reply_to,
            references=message.references,
            inbound_rows=inbound_rows,
            outbound_rows=outbound_rows,
        )

    def _log_inbound(
        self,
        message: IncomingEmail,
        *,
        thread_id: str,
        resolved_message_id: str,
    ) -> None:
        payload: dict[str, Any] = {
            "ts": message.received_at.isoformat(timespec="seconds"),
            "from": normalize_email(message.sender),
            "subject": message.subject,
            "body": message.text_body,
            "kind": "inbound",
            "thread_id": thread_id,
            "message_id": normalize_message_id(resolved_message_id),
            "in_reply_to": normalize_message_id(message.in_reply_to),
            "references": normalize_references(message.references),
            "canonical_subject": self._canonical_subject(message.subject),
        }
        append_jsonl(self.config.paths.inbound_log, payload)

    def _build_thread_context(self, thread_id: str, max_messages: int = 6) -> str:
        history: list[dict[str, Any]] = []

        for row in read_jsonl(self.config.paths.inbound_log):
            row_thread_id = str(row.get("thread_id") or "").strip()
            if row_thread_id != thread_id:
                continue

            history.append(
                {
                    "ts": str(row.get("ts") or ""),
                    "role": "sender",
                    "text": str(row.get("body") or "").strip(),
                }
            )

        for row in read_jsonl(self.config.paths.outbound_log):
            row_thread_id = str(row.get("thread_id") or "").strip()
            if row_thread_id != thread_id:
                continue

            history.append(
                {
                    "ts": str(row.get("ts") or ""),
                    "role": "assistant",
                    "text": str(row.get("body") or "").strip(),
                }
            )

        history.sort(key=lambda item: item.get("ts") or "")
        history = [item for item in history if item.get("text")]
        history = history[-max_messages:]

        if not history:
            return ""

        lines: list[str] = []
        for item in history:
            role = "Sender" if item["role"] == "sender" else "Assistant"
            text = " ".join(item["text"].split()).strip()
            if len(text) > 500:
                text = text[:497] + "..."
            lines.append(f"{role}: {text}")

        return "\n".join(lines)

    def _log_outbound(
        self,
        sender: str,
        subject: str,
        body: str,
        kind: str,
        sent: bool,
        thread_id: str,
        message_id: str | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "ts": utc_now_iso(),
            "to": sender,
            "subject": subject,
            "body": body,
            "kind": kind,
            "sent": sent,
            "thread_id": thread_id,
            "message_id": normalize_message_id(message_id),
            "in_reply_to": normalize_message_id(in_reply_to),
            "references": normalize_references(references),
            "canonical_subject": self._canonical_subject(subject),
        }
        append_jsonl(self.config.paths.outbound_log, payload)
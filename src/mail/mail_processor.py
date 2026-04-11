from __future__ import annotations

from typing import Any

from mail.chat_client import ChatClient
from mail.config import MailConfig
from mail.contacts import ContactManager
from mail.models import IncomingEmail, MailAction, ProcessingResult
from mail.smtp_client import SMTPClient
from mail.storage import ProcessedMessageStore, append_jsonl, normalize_email, utc_now_iso
from mail.templates import onboarding_body, onboarding_subject


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

        try:
            if self.processed_storage.has_message(message_id):
                return ProcessingResult(
                    sender=sender,
                    action=MailAction.ALREADY_PROCESSED,
                    email_sent=False,
                    details={"message_id": message_id},
                )

            if self.contact_manager.is_blacklisted(sender):
                self.processed_storage.add(message_id, sender, MailAction.IGNORED_BLACKLIST)
                return ProcessingResult(
                    sender=sender,
                    action=MailAction.IGNORED_BLACKLIST,
                    email_sent=False,
                    details={"message_id": message_id},
                )

            if self.contact_manager.is_whitelisted(sender):
                reply_text = self.chat_client.build_reply(
                    sender=sender,
                    subject=message.subject,
                    body=message.text_body,
                )

                fallback_name = self.config.smtp.from_name or self.config.behavior.chat_user
                reply_subject = build_reply_subject(message.subject, fallback_name)

                sent = self.smtp_client.send_plain_text(
                    to_email=sender,
                    subject=reply_subject,
                    body=reply_text,
                )

                details = {
                    "message_id": message_id,
                    "smtp_enabled": self.smtp_client.enabled,
                    "reply_subject": reply_subject,
                }

                self._log_outbound(
                    sender=sender,
                    subject=reply_subject,
                    body=reply_text,
                    kind="whitelist_reply",
                    sent=sent,
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
                self.processed_storage.add(message_id, sender, MailAction.ALREADY_NEW)
                return ProcessingResult(
                    sender=sender,
                    action=MailAction.ALREADY_NEW,
                    email_sent=False,
                    details={
                        "message_id": message_id,
                        "reason": "sender already queued for review",
                    },
                )

            new_entry = self.contact_manager.add_new(sender, note="auto-added from inbound email")
            subject = onboarding_subject(self.config.behavior.onboarding_subject)
            assistant_name = self.config.smtp.from_name or self.config.behavior.chat_user
            body = onboarding_body(sender, assistant_name)

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
            )

            self.processed_storage.add(
                message_id,
                sender,
                MailAction.ADDED_TO_NEW,
                details={
                    "message_id": message_id,
                    "onboarding_sent": sent,
                    "smtp_enabled": self.smtp_client.enabled,
                    "added_to": "new",
                    "created_at": new_entry.created_at,
                },
            )

            return ProcessingResult(
                sender=sender,
                action=MailAction.ADDED_TO_NEW,
                email_sent=sent,
                details={
                    "message_id": message_id,
                    "added_to": "new",
                    "created_at": new_entry.created_at,
                },
            )

        except Exception as exc:
            details = {
                "error": str(exc),
                "message_id": message_id,
            }
            self.processed_storage.add(message_id, sender, MailAction.ERROR, details=details)
            return ProcessingResult(
                sender=sender,
                action=MailAction.ERROR,
                email_sent=False,
                details=details,
            )

    def _resolve_message_id(self, message: IncomingEmail, sender: str) -> str:
        raw = (message.message_id or "").strip()
        if raw:
            return raw

        subject = (message.subject or "").strip()
        return f"fallback:{sender}:{subject}:{utc_now_iso()}"

    def _log_outbound(self, sender: str, subject: str, body: str, kind: str, sent: bool) -> None:
        payload: dict[str, Any] = {
            "ts": utc_now_iso(),
            "to": sender,
            "subject": subject,
            "body": body,
            "kind": kind,
            "sent": sent,
        }
        append_jsonl(self.config.paths.outbound_log, payload)
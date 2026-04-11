from __future__ import annotations

import time
from pathlib import Path

from mail.chat_client import ChatClient
from mail.config import MailConfig, MailPaths, ensure_mail_files
from mail.contacts import ContactManager
from mail.imap_client import IMAPClient
from mail.mail_processor import MailProcessor
from mail.smtp_client import SMTPClient
from mail.storage import ProcessedMessageStore


POLL_INTERVAL_SECONDS = 60


def build_config() -> MailConfig:
    """
    Version 1:
    keep config simple and explicit.
    You can replace this later with YAML/env loading.
    """
    paths = MailPaths.from_base_dir(Path("data/email"))

    return MailConfig(
        paths=paths,
        api_base_url="http://127.0.0.1:8000",
        active_profile="patricia",
        chat_user="Patricia",
        chat_timeout_seconds=30.0,
        onboarding_subject="Thanks for your message",
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_use_tls=True,
        smtp_from_email=None,
        smtp_from_name="Patricia",
    )


def build_processor(config: MailConfig) -> MailProcessor:
    ensure_mail_files(config.paths)

    contact_manager = ContactManager(config.paths)
    processed_storage = ProcessedMessageStore(config.paths.processed)

    chat_client = ChatClient(
        api_base_url=config.api_base_url,
        profile=config.active_profile,
        user_name=config.chat_user,
        timeout_seconds=config.chat_timeout_seconds,
    )

    smtp_client = SMTPClient(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        use_ssl=False,
        from_email=config.smtp_from_email,
        from_name=config.smtp_from_name,
    )

    return MailProcessor(
        config=config,
        contact_manager=contact_manager,
        processed_storage=processed_storage,
        chat_client=chat_client,
        smtp_client=smtp_client,
    )


def build_imap_client() -> IMAPClient:
    """
    Replace these values with your real IMAP settings.
    Later this can be moved into MailConfig too.
    """
    return IMAPClient(
        host="imap.example.com",
        port=993,
        username="patricia@example.com",
        password="replace-me",
        mailbox="INBOX",
        use_ssl=True,
    )


def main() -> None:
    config = build_config()
    processor = build_processor(config)
    imap_client = build_imap_client()

    print("[MAIL] Patricia mail worker started.")

    while True:
        try:
            unread_messages = imap_client.fetch_unread_messages()

            if unread_messages:
                print(f"[MAIL] Found {len(unread_messages)} unread message(s).")

            for imap_message_id, incoming in unread_messages:
                result = processor.process_message(incoming)

                print(
                    f"[MAIL] sender={result.sender!r} "
                    f"action={result.action} "
                    f"email_sent={result.email_sent}"
                )

                # Mark seen only after processing attempt.
                # Because errors are stored as processed too, this avoids endless loops.
                imap_client.mark_seen(imap_message_id)

        except Exception as exc:
            print(f"[MAIL ERROR] {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
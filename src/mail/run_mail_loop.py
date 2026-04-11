from __future__ import annotations

import argparse
import time

from mail.chat_client import ChatClient
from mail.config import MailConfig, ensure_mail_files, load_mail_config
from mail.contacts import ContactManager
from mail.imap_client import IMAPClient
from mail.mail_processor import MailProcessor
from mail.smtp_client import SMTPClient
from mail.storage import ProcessedMessageStore


def build_processor(config: MailConfig) -> MailProcessor:
    ensure_mail_files(config.paths)

    contact_manager = ContactManager(config.paths)
    processed_storage = ProcessedMessageStore(config.paths.processed)

    chat_client = ChatClient(
        api_base_url=config.behavior.api_base_url,
        profile=config.behavior.active_profile,
        user_name=config.behavior.chat_user,
        timeout_seconds=config.behavior.chat_timeout_seconds,
    )

    smtp_client = SMTPClient(
        host=config.smtp.host,
        port=config.smtp.port,
        username=config.smtp.username,
        password=config.smtp.password,
        use_tls=config.smtp.use_tls,
        use_ssl=config.smtp.use_ssl,
        from_email=config.smtp.from_email,
        from_name=config.smtp.from_name,
    )

    return MailProcessor(
        config=config,
        contact_manager=contact_manager,
        processed_storage=processed_storage,
        chat_client=chat_client,
        smtp_client=smtp_client,
    )


def build_imap_client(config: MailConfig) -> IMAPClient:
    return IMAPClient(
        host=config.imap.host,
        port=config.imap.port,
        username=config.imap.username,
        password=config.imap.password,
        mailbox=config.imap.mailbox,
        use_ssl=config.imap.use_ssl,
    )


def main() -> None:
    args = parse_args()
    config = load_mail_config(args.profile)
    processor = build_processor(config)
    imap_client = build_imap_client(config)

    print(f"[MAIL] {config.profile_name} mail worker started.")
    print(f"[MAIL] mailbox={config.imap.mailbox} poll_interval={config.imap.poll_interval_seconds}s")
    print(f"[MAIL] data_dir={config.paths.base_dir}")
    print(f"[MAIL] api_base_url={config.behavior.api_base_url}")
    print(f"[MAIL] active_profile={config.behavior.active_profile}")

    while True:
        try:
            unread_messages = imap_client.fetch_unread_messages()

            if unread_messages:
                print(f"[MAIL] Found {len(unread_messages)} unread message(s).")

            for imap_message_id, incoming in unread_messages:
                result = processor.process_message(incoming)

                print(
                    f"[MAIL] sender={result.sender!r} "
                    f"action={result.action.value} "
                    f"email_sent={result.email_sent}"
                )

                if config.behavior.mark_seen_after_processing:
                    imap_client.mark_seen(imap_message_id)

        except Exception as exc:
            print(f"[MAIL ERROR] {exc}")

        time.sleep(config.imap.poll_interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the profile-based AI mail worker.")
    parser.add_argument(
        "--profile",
        required=True,
        help="default",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
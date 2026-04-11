from mail.chat_client import ChatClient
from mail.config import MailConfig, MailPaths, ensure_mail_files
from mail.contacts import ContactManager
from mail.mail_processor import MailProcessor
from mail.models import ContactEntry, IncomingEmail, MailAction, ProcessingResult
from mail.smtp_client import SMTPClient
from mail.storage import ProcessedMessageStore

__all__ = [
    "ChatClient",
    "ContactEntry",
    "ContactManager",
    "IncomingEmail",
    "MailAction",
    "MailConfig",
    "MailPaths",
    "MailProcessor",
    "ProcessedMessageStore",
    "ProcessingResult",
    "SMTPClient",
    "ensure_mail_files",
]

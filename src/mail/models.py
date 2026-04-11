from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MailAction(str, Enum):
    IGNORED_BLACKLIST = "ignored_blacklist"
    ADDED_TO_NEW = "added_to_new"
    ALREADY_NEW = "already_new"
    REPLIED_WHITELIST = "replied_whitelist"
    ALREADY_PROCESSED = "already_processed"
    ERROR = "error"


@dataclass(slots=True)
class IncomingEmail:
    message_id: str
    sender: str
    subject: str
    text_body: str
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContactEntry:
    email: str
    created_at: str
    source: str = "mail_worker"
    note: str | None = None


@dataclass(slots=True)
class ProcessedEntry:
    message_id: str
    sender: str
    action: MailAction
    created_at: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessingResult:
    sender: str
    action: MailAction
    email_sent: bool
    details: dict[str, Any] | None = None

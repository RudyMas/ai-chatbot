from __future__ import annotations

from dataclasses import asdict

from mail.config import MailPaths
from mail.models import ContactEntry
from mail.storage import append_jsonl, load_email_set, normalize_email, read_jsonl, utc_now_iso


class ContactManager:
    def __init__(self, paths: MailPaths):
        self.paths = paths

    def is_whitelisted(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.whitelist)

    def is_blacklisted(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.blacklist)

    def is_new(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.new)

    def add_new(self, email: str, note: str | None = None) -> ContactEntry:
        entry = ContactEntry(
            email=normalize_email(email),
            created_at=utc_now_iso(),
            source="unknown_sender",
            note=note,
        )
        append_jsonl(self.paths.new, asdict(entry))
        return entry

    def list_new(self) -> list[ContactEntry]:
        out: list[ContactEntry] = []
        for row in read_jsonl(self.paths.new):
            email = row.get("email")
            created_at = row.get("created_at")
            if isinstance(email, str) and isinstance(created_at, str):
                out.append(
                    ContactEntry(
                        email=normalize_email(email),
                        created_at=created_at,
                        source=str(row.get("source") or "mail_worker"),
                        note=str(row.get("note")) if row.get("note") is not None else None,
                    )
                )
        return out

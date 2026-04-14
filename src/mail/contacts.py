from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from mail.config import MailPaths
from mail.models import ContactEntry
from mail.storage import (
    append_jsonl,
    load_email_set,
    normalize_email,
    read_jsonl,
    utc_now_iso,
    write_jsonl,
)


class ContactManager:
    def __init__(self, paths: MailPaths):
        self.paths = paths

    def is_whitelisted(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.whitelist)

    def is_blacklisted(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.blacklist)

    def is_new(self, email: str) -> bool:
        return normalize_email(email) in load_email_set(self.paths.new)

    def get_new_entry(self, email: str) -> ContactEntry | None:
        normalized = normalize_email(email)

        for row in read_jsonl(self.paths.new):
            row_email = row.get("email")
            created_at = row.get("created_at")
            if not isinstance(row_email, str) or not isinstance(created_at, str):
                continue

            if normalize_email(row_email) != normalized:
                continue

            return ContactEntry(
                email=normalized,
                created_at=created_at,
                source=str(row.get("source") or "mail_worker"),
                note=str(row.get("note")) if row.get("note") is not None else None,
                onboarding_sent_at=_clean_optional_string(row.get("onboarding_sent_at")),
                last_pending_reply_at=_clean_optional_string(row.get("last_pending_reply_at")),
            )

        return None

    def add_new(self, email: str, note: str | None = None) -> ContactEntry:
        existing = self.get_new_entry(email)
        if existing is not None:
            return existing

        entry = ContactEntry(
            email=normalize_email(email),
            created_at=utc_now_iso(),
            source="unknown_sender",
            note=note,
        )
        append_jsonl(self.paths.new, asdict(entry))
        return entry

    def mark_onboarding_sent(self, email: str, sent_at: str | None = None) -> ContactEntry | None:
        return self._update_new_entry(
            email,
            {
                "onboarding_sent_at": sent_at or utc_now_iso(),
            },
        )

    def mark_pending_reply_sent(self, email: str, sent_at: str | None = None) -> ContactEntry | None:
        return self._update_new_entry(
            email,
            {
                "last_pending_reply_at": sent_at or utc_now_iso(),
            },
        )

    def should_send_pending_reply(self, email: str, cooldown_hours: int) -> bool:
        entry = self.get_new_entry(email)
        if entry is None:
            return False

        if not entry.last_pending_reply_at:
            return True

        last_sent = _parse_iso_datetime(entry.last_pending_reply_at)
        if last_sent is None:
            return True

        return datetime.now(timezone.utc) - last_sent >= timedelta(hours=max(0, cooldown_hours))

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
                        onboarding_sent_at=_clean_optional_string(row.get("onboarding_sent_at")),
                        last_pending_reply_at=_clean_optional_string(row.get("last_pending_reply_at")),
                    )
                )

        return out

    def _update_new_entry(self, email: str, updates: dict[str, str | None]) -> ContactEntry | None:
        normalized = normalize_email(email)
        rows = read_jsonl(self.paths.new)
        updated = False

        for row in rows:
            row_email = row.get("email")
            if not isinstance(row_email, str):
                continue

            if normalize_email(row_email) != normalized:
                continue

            for key, value in updates.items():
                row[key] = value
            updated = True
            break

        if not updated:
            return None

        write_jsonl(self.paths.new, rows)
        return self.get_new_entry(normalized)

    def get_contact_row(self, email: str, status: str) -> dict[str, object] | None:
        normalized = normalize_email(email)

        path = None
        if status == "new":
            path = self.paths.new
        elif status == "whitelist":
            path = self.paths.whitelist
        elif status == "blacklist":
            path = self.paths.blacklist

        if path is None:
            return None

        for row in read_jsonl(path):
            row_email = row.get("email")
            if not isinstance(row_email, str):
                continue

            if normalize_email(row_email) != normalized:
                continue

            return dict(row)

        return None

    def get_contact_note(self, email: str, status: str) -> str | None:
        row = self.get_contact_row(email, status)
        if not row:
            return None

        note = row.get("note")
        if note is None:
            return None

        text = str(note).strip()
        return text or None

    def list_whitelist(self) -> list[ContactEntry]:
        out: list[ContactEntry] = []

        for row in read_jsonl(self.paths.whitelist):
            email = row.get("email")
            created_at = row.get("created_at")
            if isinstance(email, str):
                out.append(
                    ContactEntry(
                        email=normalize_email(email),
                        created_at=str(created_at or ""),
                        source=str(row.get("source") or "mail_worker"),
                        note=str(row.get("note")) if row.get("note") is not None else None,
                        onboarding_sent_at=_clean_optional_string(row.get("onboarding_sent_at")),
                        last_pending_reply_at=_clean_optional_string(row.get("last_pending_reply_at")),
                    )
                )

        return out


def _clean_optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from mail.models import MailAction, ProcessedEntry


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(email: str | None) -> str:
    if not email:
        return ""
    return email.strip().lower()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                records.append(row)

    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_jsonl_many(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_email_set(path: Path) -> set[str]:
    emails: set[str] = set()
    for row in read_jsonl(path):
        value = row.get("email")
        normalized = normalize_email(value if isinstance(value, str) else "")
        if normalized:
            emails.add(normalized)
    return emails


class ProcessedMessageStore:
    def __init__(self, processed_path: Path):
        self.processed_path = processed_path

    def has_message(self, message_id: str | None) -> bool:
        normalized_message_id = (message_id or "").strip()
        if not normalized_message_id:
            return False

        for row in read_jsonl(self.processed_path):
            row_message_id = row.get("message_id")
            if isinstance(row_message_id, str) and row_message_id.strip() == normalized_message_id:
                return True

        return False

    def add(
        self,
        message_id: str,
        sender: str,
        action: MailAction,
        details: dict[str, Any] | None = None,
    ) -> ProcessedEntry:
        clean_message_id = (message_id or "").strip()
        if not clean_message_id:
            raise ValueError("message_id is required")

        entry = ProcessedEntry(
            message_id=clean_message_id,
            sender=normalize_email(sender),
            action=action,
            created_at=utc_now_iso(),
            details=details or {},
        )

        payload = asdict(entry)
        payload["action"] = entry.action.value
        append_jsonl(self.processed_path, payload)

        return entry
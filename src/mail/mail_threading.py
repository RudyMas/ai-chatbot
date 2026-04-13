from __future__ import annotations

import hashlib
from typing import Any

from mail.storage import normalize_email


def normalize_message_id(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip("<>").strip().lower()


def normalize_references(values: list[str] | None) -> list[str]:
    if not values:
        return []

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        normalized = normalize_message_id(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


def canonicalize_subject(subject: str | None) -> str:
    text = (subject or "").strip()
    if not text:
        return "(no subject)"

    prefixes = ("re:", "fw:", "fwd:", "aw:")
    current = text

    changed = True
    while changed:
        changed = False
        stripped = current.lstrip()
        lowered = stripped.lower()

        for prefix in prefixes:
            if lowered.startswith(prefix):
                current = stripped[len(prefix):].strip()
                changed = True
                break

    current = " ".join(current.split())
    return current or "(no subject)"


def make_thread_id(
    profile_name: str,
    sender_email: str,
    canonical_subject: str,
    timestamp: str,
) -> str:
    bucket = (timestamp or "")[:7] or "unknown"
    seed = (
        f"{(profile_name or '').strip().lower()}|"
        f"{normalize_email(sender_email)}|"
        f"{(canonical_subject or '').strip().lower()}|"
        f"{bucket}"
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"thr_{digest}"


def resolve_thread_id(
    *,
    profile_name: str,
    sender_email: str,
    subject: str | None,
    timestamp: str,
    message_id: str | None,
    in_reply_to: str | None,
    references: list[str] | None,
    inbound_rows: list[dict[str, Any]],
    outbound_rows: list[dict[str, Any]],
) -> str:
    canonical_subject = canonicalize_subject(subject)
    normalized_sender = normalize_email(sender_email)
    normalized_message_id = normalize_message_id(message_id)
    normalized_in_reply_to = normalize_message_id(in_reply_to)
    normalized_references = set(normalize_references(references))

    all_rows = list(inbound_rows) + list(outbound_rows)

    # 1. Exact match via In-Reply-To
    if normalized_in_reply_to:
        for row in reversed(all_rows):
            row_message_id = normalize_message_id(row.get("message_id"))
            row_thread_id = str(row.get("thread_id") or "").strip()
            if row_message_id == normalized_in_reply_to and row_thread_id:
                return row_thread_id

    # 2. Exact match via References
    if normalized_references:
        for row in reversed(all_rows):
            row_message_id = normalize_message_id(row.get("message_id"))
            row_thread_id = str(row.get("thread_id") or "").strip()
            if row_message_id in normalized_references and row_thread_id:
                return row_thread_id

    # 3. Soft match via sender + canonical subject
    candidates: list[str] = []

    for row in reversed(all_rows):
        row_thread_id = str(row.get("thread_id") or "").strip()
        if not row_thread_id:
            continue

        row_subject = canonicalize_subject(row.get("subject"))
        if row_subject != canonical_subject:
            continue

        row_from = normalize_email(str(row.get("from") or ""))
        row_to = normalize_email(str(row.get("to") or ""))

        if normalized_sender not in {row_from, row_to}:
            continue

        row_message_id = normalize_message_id(row.get("message_id"))
        if normalized_message_id and row_message_id == normalized_message_id:
            continue

        candidates.append(row_thread_id)

    unique_candidates = list(dict.fromkeys(candidates))
    if len(unique_candidates) == 1:
        return unique_candidates[0]

    # 4. New thread
    return make_thread_id(
        profile_name=profile_name,
        sender_email=normalized_sender,
        canonical_subject=canonical_subject,
        timestamp=timestamp,
    )
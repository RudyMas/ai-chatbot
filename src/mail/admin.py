from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from bot.profiles import list_profiles
from mail.config import MailConfig, load_mail_config
from mail.storage import normalize_email, read_jsonl, utc_now_iso, write_jsonl

ContactStatus = Literal["new", "whitelist", "blacklist"]


class MoveContactIn(BaseModel):
    email: str
    from_status: ContactStatus
    to_status: ContactStatus


class RemoveContactIn(BaseModel):
    email: str
    from_status: ContactStatus


def register_admin_routes(app: FastAPI, root_dir: Path) -> None:
    web_dir = root_dir / "web"

    @app.get("/admin", response_class=HTMLResponse)
    def admin_index() -> HTMLResponse:
        html_path = web_dir / "admin.html"
        if not html_path.exists():
            return HTMLResponse("<h1>Mail Admin</h1><p>Place web/admin.html to use the admin UI.</p>")
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/admin/api/profiles")
    def admin_profiles() -> dict[str, Any]:
        active = []
        for profile_name in ["default"] + list_profiles():
            try:
                cfg = load_mail_config(profile_name)
                active.append(
                    {
                        "profile": profile_name,
                        "base_dir": str(cfg.paths.base_dir),
                        "from_email": cfg.smtp.from_email,
                    }
                )
            except Exception:
                # Skip profiles that do not have email enabled/configured
                continue

        return {"profiles": active}

    @app.get("/admin/api/{profile_name}/contacts")
    def admin_contacts(profile_name: str, status: ContactStatus) -> dict[str, Any]:
        cfg = _get_mail_config(profile_name)
        rows = _list_contacts(cfg, status)
        return {
            "profile": profile_name,
            "status": status,
            "count": len(rows),
            "items": rows,
        }

    @app.post("/admin/api/{profile_name}/contacts/move")
    def admin_move_contact(profile_name: str, payload: MoveContactIn) -> dict[str, Any]:
        cfg = _get_mail_config(profile_name)

        email = normalize_email(payload.email)
        if not email:
            raise HTTPException(status_code=400, detail="email is required")

        if payload.from_status == payload.to_status:
            raise HTTPException(status_code=400, detail="from_status and to_status must differ")

        moved = _move_contact(cfg, email, payload.from_status, payload.to_status)
        if not moved:
            raise HTTPException(status_code=404, detail="Contact not found")

        return {
            "ok": True,
            "profile": profile_name,
            "email": email,
            "from_status": payload.from_status,
            "to_status": payload.to_status,
        }

    @app.post("/admin/api/{profile_name}/contacts/remove")
    def admin_remove_contact(profile_name: str, payload: RemoveContactIn) -> dict[str, Any]:
        cfg = _get_mail_config(profile_name)

        email = normalize_email(payload.email)
        if not email:
            raise HTTPException(status_code=400, detail="email is required")

        removed = _remove_contact(cfg, email, payload.from_status)
        if not removed:
            raise HTTPException(status_code=404, detail="Contact not found")

        return {
            "ok": True,
            "profile": profile_name,
            "email": email,
            "from_status": payload.from_status,
        }


def _get_mail_config(profile_name: str) -> MailConfig:
    try:
        return load_mail_config(profile_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _path_for_status(cfg: MailConfig, status: ContactStatus) -> Path:
    if status == "new":
        return cfg.paths.new
    if status == "whitelist":
        return cfg.paths.whitelist
    if status == "blacklist":
        return cfg.paths.blacklist
    raise ValueError(f"Unsupported status: {status}")


def _list_contacts(cfg: MailConfig, status: ContactStatus) -> list[dict[str, Any]]:
    path = _path_for_status(cfg, status)
    items: list[dict[str, Any]] = []

    for row in read_jsonl(path):
        email = normalize_email(str(row.get("email") or ""))
        if not email:
            continue

        item = dict(row)
        item["email"] = email
        item["status"] = status

        item.setdefault("created_at", row.get("created_at"))
        item.setdefault("source", row.get("source"))
        item.setdefault("note", row.get("note"))
        item.setdefault("onboarding_sent_at", row.get("onboarding_sent_at"))
        item.setdefault("last_pending_reply_at", row.get("last_pending_reply_at"))
        item.setdefault("updated_at", row.get("updated_at"))

        items.append(item)

    items.sort(
        key=lambda x: (
            str(x.get("updated_at") or ""),
            str(x.get("last_pending_reply_at") or ""),
            str(x.get("onboarding_sent_at") or ""),
            str(x.get("created_at") or ""),
        ),
        reverse=True,
    )
    return items


def _move_contact(
    cfg: MailConfig,
    email: str,
    from_status: ContactStatus,
    to_status: ContactStatus,
) -> bool:
    from_path = _path_for_status(cfg, from_status)
    to_path = _path_for_status(cfg, to_status)

    source_rows = read_jsonl(from_path)
    target_rows = read_jsonl(to_path)

    moved_row: dict[str, Any] | None = None
    kept_rows: list[dict[str, Any]] = []

    for row in source_rows:
        row_email = normalize_email(str(row.get("email") or ""))
        if moved_row is None and row_email == email:
            moved_row = dict(row)
        else:
            kept_rows.append(row)

    if moved_row is None:
        return False

    # Remove duplicate if already present in target
    deduped_target: list[dict[str, Any]] = []
    for row in target_rows:
        row_email = normalize_email(str(row.get("email") or ""))
        if row_email != email:
            deduped_target.append(row)

    moved_row["email"] = email
    moved_row["updated_at"] = utc_now_iso()
    deduped_target.append(moved_row)

    write_jsonl(from_path, kept_rows)
    write_jsonl(to_path, deduped_target)
    return True


def _remove_contact(
    cfg: MailConfig,
    email: str,
    from_status: ContactStatus,
) -> bool:
    path = _path_for_status(cfg, from_status)
    rows = read_jsonl(path)

    kept_rows: list[dict[str, Any]] = []
    removed = False

    for row in rows:
        row_email = normalize_email(str(row.get("email") or ""))
        if row_email == email:
            removed = True
            continue
        kept_rows.append(row)

    if not removed:
        return False

    write_jsonl(path, kept_rows)
    return True
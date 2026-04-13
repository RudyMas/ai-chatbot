from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from bot.profiles import load_profile

ROOT = Path(__file__).parents[0]


@dataclass(slots=True)
class MailPaths:
    base_dir: Path
    whitelist: Path
    blacklist: Path
    new: Path
    processed: Path
    inbound_log: Path
    outbound_log: Path

    @classmethod
    def from_base_dir(cls, base_dir: str | Path) -> "MailPaths":
        base = Path(base_dir)
        return cls(
            base_dir=base,
            whitelist=base / "whitelist.jsonl",
            blacklist=base / "blacklist.jsonl",
            new=base / "new.jsonl",
            processed=base / "processed.jsonl",
            inbound_log=base / "inbound_log.jsonl",
            outbound_log=base / "outbound_log.jsonl",
        )


@dataclass(slots=True)
class IMAPSettings:
    host: str
    port: int = 993
    username: str | None = None
    password: str | None = None
    mailbox: str = "INBOX"
    use_ssl: bool = True
    poll_interval_seconds: int = 60


@dataclass(slots=True)
class SMTPSettings:
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str | None = None
    from_name: str = "Assistant"

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_email)


@dataclass(slots=True)
class MailBehaviorSettings:
    api_base_url: str = "http://127.0.0.1:8000"
    active_profile: str = "default"
    chat_user: str = "Assistant"
    chat_timeout_seconds: float = 30.0
    onboarding_subject: str = "Thanks for your message"
    mark_seen_after_processing: bool = True
    send_pending_reply: bool = False
    pending_reply_cooldown_hours: int = 24
    signature: str | None = None


@dataclass(slots=True)
class MailConfig:
    profile_name: str
    paths: MailPaths
    imap: IMAPSettings
    smtp: SMTPSettings
    behavior: MailBehaviorSettings


def ensure_mail_files(paths: MailPaths) -> None:
    paths.base_dir.mkdir(parents=True, exist_ok=True)

    for path in (
        paths.whitelist,
        paths.blacklist,
        paths.new,
        paths.processed,
        paths.inbound_log,
        paths.outbound_log,
    ):
        if not path.exists():
            path.touch()


def load_mail_config(profile_name: str) -> MailConfig:
    _, raw_cfg, _ = load_profile(profile_name)

    email_cfg = raw_cfg.get("email") or {}
    if not isinstance(email_cfg, dict):
        raise ValueError(f"Profile '{profile_name}' has invalid email configuration.")

    enabled = bool(email_cfg.get("enabled", False))
    if not enabled:
        raise ValueError(f"Email is not enabled for profile '{profile_name}'.")

    files_cfg = email_cfg.get("files") or {}
    if not isinstance(files_cfg, dict):
        files_cfg = {}

    base_dir = files_cfg.get("base_dir") or f"data/email/{profile_name}"
    base_path = Path(base_dir)
    if not base_path.is_absolute():
        base_path = ROOT / base_path
    paths = MailPaths.from_base_dir(base_path)

    imap_cfg = email_cfg.get("imap") or {}
    if not isinstance(imap_cfg, dict):
        raise ValueError(f"Profile '{profile_name}' has invalid email.imap configuration.")

    smtp_cfg = email_cfg.get("smtp") or {}
    if not isinstance(smtp_cfg, dict):
        raise ValueError(f"Profile '{profile_name}' has invalid email.smtp configuration.")

    behavior_cfg = email_cfg.get("behavior") or {}
    if not isinstance(behavior_cfg, dict):
        raise ValueError(f"Profile '{profile_name}' has invalid email.behavior configuration.")

    imap_host = _require_string(imap_cfg, "host", f"profile '{profile_name}' email.imap.host")
    imap_password = _resolve_secret(
        direct_value=imap_cfg.get("password"),
        env_name=imap_cfg.get("password_env"),
    )
    smtp_password = _resolve_secret(
        direct_value=smtp_cfg.get("password"),
        env_name=smtp_cfg.get("password_env"),
    )

    imap = IMAPSettings(
        host=imap_host,
        port=int(imap_cfg.get("port", 993)),
        username=_optional_string(imap_cfg.get("username")),
        password=imap_password,
        mailbox=str(imap_cfg.get("mailbox", "INBOX")),
        use_ssl=bool(imap_cfg.get("use_ssl", True)),
        poll_interval_seconds=int(imap_cfg.get("poll_interval_seconds", 60)),
    )

    smtp = SMTPSettings(
        host=_optional_string(smtp_cfg.get("host")),
        port=int(smtp_cfg.get("port", 587)),
        username=_optional_string(smtp_cfg.get("username")),
        password=smtp_password,
        use_tls=bool(smtp_cfg.get("use_tls", True)),
        use_ssl=bool(smtp_cfg.get("use_ssl", False)),
        from_email=_optional_string(smtp_cfg.get("from_email")),
        from_name=str(smtp_cfg.get("from_name", profile_name.capitalize())),
    )

    behavior = MailBehaviorSettings(
        api_base_url=str(behavior_cfg.get("api_base_url", "http://127.0.0.1:8000")),
        active_profile=str(behavior_cfg.get("active_profile", profile_name)),
        chat_user=str(behavior_cfg.get("chat_user", profile_name.capitalize())),
        chat_timeout_seconds=float(behavior_cfg.get("chat_timeout_seconds", 30.0)),
        onboarding_subject=str(behavior_cfg.get("onboarding_subject", "Thanks for your message")),
        mark_seen_after_processing=bool(behavior_cfg.get("mark_seen_after_processing", True)),
        send_pending_reply=bool(behavior_cfg.get("send_pending_reply", False)),
        pending_reply_cooldown_hours=int(behavior_cfg.get("pending_reply_cooldown_hours", 24)),
        signature=_optional_string(behavior_cfg.get("signature")),
    )

    return MailConfig(
        profile_name=profile_name,
        paths=paths,
        imap=imap,
        smtp=smtp,
        behavior=behavior,
    )


def _resolve_secret(direct_value: Any, env_name: Any) -> str | None:
    direct = _optional_string(direct_value)
    if direct:
        return direct

    env = _optional_string(env_name)
    if env:
        return os.getenv(env)

    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_string(section: dict[str, Any], key: str, label: str) -> str:
    value = section.get(key)
    text = _optional_string(value)
    if not text:
        raise ValueError(f"Missing required {label}.")
    return text
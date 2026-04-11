from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MailPaths:
    base_dir: Path
    whitelist: Path
    blacklist: Path
    new: Path
    processed: Path
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
            outbound_log=base / "outbound_log.jsonl",
        )


@dataclass(slots=True)
class MailConfig:
    paths: MailPaths
    chat_endpoint: str = "http://127.0.0.1:8000/chat"
    chat_user: str = "Patricia"
    onboarding_subject: str = "Thanks for your message"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_email: str | None = None


def ensure_mail_files(paths: MailPaths) -> None:
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        paths.whitelist,
        paths.blacklist,
        paths.new,
        paths.processed,
        paths.outbound_log,
    ):
        if not path.exists():
            path.touch()

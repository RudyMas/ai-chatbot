from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
from typing import Optional


@dataclass(slots=True)
class SMTPClient:
    host: str | None
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str | None = None
    from_name: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_email)

    def send_plain_text(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[list[str]] = None,
    ) -> bool:
        if not self.enabled:
            return False

        clean_body = (body or "").strip()
        if not clean_body:
            clean_body = "(empty response)"

        message = EmailMessage()

        if self.from_name:
            message["From"] = f"{self.from_name} <{self.from_email}>"
        else:
            message["From"] = self.from_email

        message["To"] = to_email
        message["Subject"] = subject

        if message_id:
            message["Message-ID"] = message_id

        if in_reply_to:
            message["In-Reply-To"] = in_reply_to

        if references:
            clean_refs = [r.strip() for r in references if isinstance(r, str) and r.strip()]
            if clean_refs:
                message["References"] = " ".join(clean_refs)

        if reply_to:
            message["Reply-To"] = reply_to

        message.set_content(clean_body)

        try:
            if self.use_ssl:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=20)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=20)

            with smtp:
                smtp.ehlo()

                if self.use_tls and not self.use_ssl:
                    smtp.starttls()
                    smtp.ehlo()

                if self.username:
                    smtp.login(self.username, self.password or "")

                smtp.send_message(message)

            return True

        except Exception as exc:
            print(f"[SMTP ERROR] Failed to send email to {to_email}: {exc}")
            return False
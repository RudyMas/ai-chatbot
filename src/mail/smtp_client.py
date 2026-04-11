from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib


@dataclass(slots=True)
class SMTPClient:
    host: str | None
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    from_email: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_email)

    def send_plain_text(self, to_email: str, subject: str, body: str) -> bool:
        if not self.enabled:
            return False

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(message)

        return True

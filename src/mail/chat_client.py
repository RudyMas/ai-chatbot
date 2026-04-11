from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(slots=True)
class ChatClient:
    endpoint: str
    user_name: str = "Patricia"
    timeout_seconds: float = 30.0

    def build_reply(self, sender: str, subject: str, body: str) -> str:
        prompt = (
            "Write a concise plain-text email reply as Patricia. "
            f"Sender: {sender}\n"
            f"Subject: {subject}\n"
            f"Message:\n{body}"
        )
        payload = {
            "message": prompt,
            "user": self.user_name,
            "session": f"mail:{sender}",
        }
        response = requests.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("/chat response missing text answer")
        return answer.strip()

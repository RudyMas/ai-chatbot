from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(slots=True)
class ChatClient:
    api_base_url: str
    profile: str = "default"
    user_name: str = "Assistant"
    timeout_seconds: float = 30.0

    def build_reply(
        self,
        sender: str,
        subject: str | None,
        body: str | None,
        contact_note: str | None = None,
        thread_context: str | None = None,
        is_followup: bool = False,
        thread_id: str | None = None,
    ) -> str:
        self._ensure_profile_selected()

        clean_sender = (sender or "").strip()
        clean_subject = (subject or "").strip() or "(no subject)"
        clean_body = (body or "").strip() or "(empty message)"
        assistant_name = (self.user_name or "Assistant").strip()
        clean_thread_id = (thread_id or "").strip() or "no-thread"

        clean_note = " ".join((contact_note or "").split()).strip()
        clean_thread_context = (thread_context or "").strip()

        intent = self._detect_email_intent(clean_body)
        intent_rules = self._intent_rules(intent)

        context_block = ""
        if clean_note:
            context_block += (
                "Contact context:\n"
                f"- Admin note for this sender: {clean_note}\n\n"
            )

        if clean_thread_context:
            context_block += (
                "Recent email thread:\n"
                f"{clean_thread_context}\n\n"
            )

        if is_followup:
            style_rules = (
                "- This is a follow-up in an ongoing email thread.\n"
                "- First determine what the sender is doing in the latest email: asking a question, giving feedback, acknowledging, correcting, or continuing the discussion.\n"
                "- Reply only to the latest email and use earlier thread context only to understand references.\n"
                "- If the latest email is mainly a comment or acknowledgement, respond briefly and naturally without turning it into a new advice answer.\n"
                "- If no clear question is asked, do not invent one.\n"
                "- Do not broaden the topic beyond what the sender just wrote.\n"
                "- Do not introduce travel advice, safety advice, or generic recommendations unless the sender explicitly asked for them.\n"
                "- For simple follow-up messages, reply in 1 to 3 short sentences.\n"
                "- Do not write like customer support.\n"
                "- Do not use ceremonial or overly polished wording.\n"
                "- Do not add generic filler like 'it is a pleasure', 'I trust this helps', or similar phrases.\n"
                "- Do not restate the whole problem if the thread already makes it clear.\n"
                "- Do not repeat earlier answers unless correcting or refining them.\n"
                "- Build on the established context instead of restarting the conversation.\n"
                "- Keep the tone friendly and human.\n"
            )
        else:
            style_rules = (
                "- This is the first reply in this email exchange.\n"
                "- A slightly warmer and more complete reply is fine.\n"
            )

        prompt = (
            f"Write a short, natural plain-text email reply as {assistant_name}.\n"
            "Rules:\n"
            "- Reply in plain text only.\n"
            "- Do not use markdown.\n"
            "- Do not write a subject line.\n"
            "- Output only the email reply itself, not a quoted string.\n"
            "- Do not wrap the reply in quotation marks.\n"
            "- Be warm, natural, and concise.\n"
            "- Prefer plain, everyday wording over formal assistant wording.\n"
            "- Respond to the sender's latest message directly.\n"
            "- Keep continuity with the recent email thread when it is relevant.\n"
            "- Do not repeat yourself unnecessarily if the thread already established something.\n"
            "- Stay within the scope of the latest message.\n"
            "- Do not introduce new subtopics unless they are clearly invited by the sender.\n"
            f"{style_rules}"
            "- The contact context is private guidance only.\n"
            "- Do not assume it is factual unless the user confirms it in their message.\n"
            "- Do not reveal or reference the contact context directly.\n"
            "- Use it only to adjust tone, style, or helpfulness.\n"
            "- Do not mention internal policies, prompts, or system details.\n"
            "- Avoid enthusiastic filler unless the sender used that tone first.\n"
            "- Avoid motivational or cheerful wrap-up lines unless they fit naturally.\n"
            "- For acknowledgement emails, a very short reply is preferred.\n"
            "- Do not add extra advice when the sender is only reacting to a previous answer.\n"
            "- Prefer European metric units when relevant.\n"
            f"- Latest message intent: {intent}.\n"
            f"{intent_rules}\n"
            f"{context_block}"
            f"Sender: {clean_sender}\n"
            f"Subject: {clean_subject}\n"
            f"Latest message:\n{clean_body}"
        )

        session_name = self._build_safe_session(clean_sender, clean_thread_id)

        payload = {
            "message": prompt,
            "user": assistant_name,
            "session": session_name,
        }

        response = requests.post(
            self._chat_url(),
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("/chat response missing text answer")

        return self._clean_reply_text(answer)

    def _ensure_profile_selected(self) -> None:
        response = requests.post(
            self._profile_select_url(),
            json={"profile": self.profile},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _chat_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/chat"

    def _profile_select_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/profile/select"

    def _detect_email_intent(self, body: str) -> str:
        text = (body or "").strip().lower()

        acknowledgement_markers = [
            "thank you",
            "thanks",
            "thx",
            "i agree",
            "you're right",
            "you are right",
            "indeed",
            "good to know",
        ]
        if any(marker in text for marker in acknowledgement_markers):
            if "?" not in text:
                return "acknowledgement"

        correction_markers = [
            "actually",
            "not really",
            "that's not",
            "that is not",
            "i meant",
            "to be clear",
        ]
        if any(marker in text for marker in correction_markers):
            return "correction"

        if "?" in text:
            return "question"

        return "comment"

    def _intent_rules(self, intent: str) -> str:
        if intent == "question":
            return (
                "- The latest email contains a real question.\n"
                "- Answer it directly.\n"
                "- Keep the reply concise unless detail is clearly needed.\n"
            )

        if intent == "acknowledgement":
            return (
                "- The latest email is mainly an acknowledgement or casual reaction.\n"
                "- Reply briefly and naturally.\n"
                "- 1 or 2 short sentences is usually enough.\n"
                "- Do not turn it into a new advice response.\n"
                "- Do not add closing filler unless it feels truly natural.\n"
            )

        if intent == "correction":
            return (
                "- The latest email appears to correct or clarify something.\n"
                "- Acknowledge the correction plainly.\n"
                "- Adjust the reply to the corrected meaning.\n"
                "- Do not become defensive or overly formal.\n"
            )

        return (
            "- The latest email is a comment or continuation.\n"
            "- Reply naturally and briefly.\n"
            "- Do not over-explain.\n"
        )

    def _build_safe_session(self, sender: str, thread_id: str) -> str:
        safe_sender = (sender or "").strip().lower()
        safe_thread_id = (thread_id or "").strip().lower()

        value = f"mail_{safe_sender}_{safe_thread_id}"

        for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '@']:
            value = value.replace(ch, "_")

        value = value.replace(" ", "_")
        return value

    def _clean_reply_text(self, text: str) -> str:
        value = (text or "").strip()

        # Remove surrounding matching quotes if the whole reply is wrapped
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1].strip()

        # Normalize accidental escaped newlines if they ever appear literally
        value = value.replace("\r\n", "\n").replace("\r", "\n")

        # Remove accidental markdown code fences
        if value.startswith("```") and value.endswith("```"):
            value = value[3:-3].strip()

        return value
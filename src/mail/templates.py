from __future__ import annotations


def onboarding_subject(configured_subject: str | None) -> str:
    if configured_subject and configured_subject.strip():
        return configured_subject.strip()

    return "Thanks for your message"


def onboarding_body(sender: str, assistant_name: str, signature: str | None = None) -> str:
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"Thanks for contacting {name}. Your message has been received and queued for review. "
        f"A team member may follow up after your sender address is approved.\n\n"
        f"Sender on file: {sender}\n\n"
        f"{build_signature(signature, name)}\n\n"
        f"Disclaimer:\n"
        f"You are communicating with an AI. Its responses are generated automatically and should be taken lightly and not as factual or professional advice. While it is designed to be respectful, it is not filtered and may occasionally say things you don’t agree with. This project is meant for fun and experimentation. If something feels off or inappropriate, feel free to report it at support@young-ai.be"
    )


def pending_approval_body(sender: str, assistant_name: str, signature: str | None = None) -> str:
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"Your previous message to {name} is still pending approval. "
        f"You will receive a reply once your sender address has been approved.\n\n"
        f"Sender on file: {sender}\n\n"
        f"{build_signature(signature, name)}"
    )


def error_body(assistant_name: str, signature: str | None = None) -> str:
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"An unexpected error occurred while processing your message. "
        f"Please try again later.\n\n"
        f"{build_signature(signature, name)}"
    )


def build_signature(signature: str | None, assistant_name: str) -> str:
    if signature and signature.strip():
        return signature.strip()

    name = (assistant_name or "Assistant").strip()
    return f"Regards,\n{name} Mail Worker"
from __future__ import annotations


def onboarding_subject(configured_subject: str | None) -> str:
    """
    Return the onboarding subject.
    Falls back to a default if not configured.
    """
    if configured_subject and configured_subject.strip():
        return configured_subject.strip()

    return "Thanks for your message"


def onboarding_body(sender: str, assistant_name: str) -> str:
    """
    First-contact email sent to unknown senders.
    """
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"Thanks for contacting {name}. Your message has been received and queued for review. "
        f"A team member may follow up after your sender address is approved.\n\n"
        f"Sender on file: {sender}\n\n"
        f"Regards,\n"
        f"{name} Mail Worker"
    )


def pending_approval_body(sender: str, assistant_name: str) -> str:
    """
    Optional: message for senders who are still in 'new' and try again.
    Not used yet, but ready for future use.
    """
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"Your previous message to {name} is still pending approval. "
        f"You will receive a reply once your sender address has been approved.\n\n"
        f"Sender on file: {sender}\n\n"
        f"Regards,\n"
        f"{name} Mail Worker"
    )


def error_body(assistant_name: str) -> str:
    """
    Optional fallback error message (not used yet).
    """
    name = (assistant_name or "Assistant").strip()

    return (
        f"Hi,\n\n"
        f"An unexpected error occurred while processing your message. "
        f"Please try again later.\n\n"
        f"Regards,\n"
        f"{name} Mail Worker"
    )
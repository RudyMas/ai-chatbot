from __future__ import annotations


def onboarding_subject(default_subject: str) -> str:
    return default_subject.strip() or "Thanks for your message"


def onboarding_body(sender_email: str) -> str:
    return (
        "Hi,\n\n"
        "Thanks for contacting Patricia. Your message has been received and queued for review. "
        "A team member may follow up after your sender address is approved.\n\n"
        f"Sender on file: {sender_email}\n\n"
        "Regards,\n"
        "Patricia Mail Worker"
    )

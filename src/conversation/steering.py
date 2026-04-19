import re
from difflib import SequenceMatcher

LOOP_PHRASES = [
    "talk soon",
    "promise",
    "i promise",
    "don't worry",
    "dont worry",
    "haha",
    "you better",
    "i wouldn't dream of it",
    "i wouldnt dream of it",
    "good",
    "okay",
    "ok",
]

PROGRESS_MARKERS = [
    "what if",
    "we could",
    "let's",
    "lets",
    "maybe we should",
    "do you want",
    "should we",
    "how about",
    "option",
    "plan",
    "step",
    "first",
    "next",
    "instead",
    "or we could",
    "which one",
    "do we want",
    "start with",
    "go with",
    "narrow it down",
    "here's the idea",
    "heres the idea",
]

IDEA_MARKERS = [
    "idea",
    "twist",
    "prank",
    "plan",
    "scenario",
    "version",
    "maybe",
    "what if",
    "imagine",
    "chaos",
]

QUESTION_WORDS = [
    "what",
    "why",
    "how",
    "when",
    "which",
    "who",
    "where",
]


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s'?]", "", text)
    return text


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_low_information(text: str) -> bool:
    t = normalize_text(text)
    words = t.split()

    if len(words) <= 6:
        return True

    if len(words) <= 14 and any(phrase in t for phrase in LOOP_PHRASES):
        return True

    return False


def contains_question(reply: str) -> bool:
    if "?" in reply:
        return True

    t = normalize_text(reply)
    return any(f"{word} " in t for word in QUESTION_WORDS)


def has_progress_marker(reply: str) -> bool:
    t = normalize_text(reply)
    return any(marker in t for marker in PROGRESS_MARKERS)


def has_new_idea_signal(reply: str) -> bool:
    t = normalize_text(reply)
    return any(marker in t for marker in IDEA_MARKERS)


def conversation_is_looping(messages: list[str]) -> bool:
    """
    Expects the most recent message bodies in chronological order.
    Only plain text bodies are needed.
    """
    if len(messages) < 4:
        return False

    recent = [normalize_text(m) for m in messages[-4:] if m.strip()]
    if len(recent) < 4:
        return False

    low_info_count = sum(1 for m in recent if is_low_information(m))
    if low_info_count >= 3:
        return True

    similar_pairs = 0
    for i in range(len(recent) - 1):
        if similarity(recent[i], recent[i + 1]) >= 0.72:
            similar_pairs += 1
    if similar_pairs >= 2:
        return True

    phrase_hits = sum(
        1 for m in recent
        if any(phrase in m for phrase in LOOP_PHRASES)
    )
    if phrase_hits >= 3:
        return True

    return False


def reply_has_progress(reply: str, previous_message: str | None = None) -> bool:
    """
    Checks whether the generated reply actually moves the conversation forward.
    A reply should do at least one of these:
    - ask a real question
    - propose a concrete next step
    - add a fresh idea or twist
    - offer a meaningful option or direction
    """
    if not reply or not reply.strip():
        return False

    t = normalize_text(reply)
    word_count = len(t.split())

    if word_count < 8:
        return False

    if previous_message:
        prev = normalize_text(previous_message)
        if similarity(t, prev) >= 0.75:
            return False

    has_question = contains_question(reply)
    has_progress = has_progress_marker(reply)
    has_idea = has_new_idea_signal(reply)

    if has_question or has_progress or has_idea:
        return True

    return False


def build_hidden_guidance(
    recent_messages: list[str],
    current_state: str | None = None,
    sender_name: str | None = None,
) -> str:
    parts: list[str] = []

    if current_state:
        parts.append(
            f"Current thread state: {current_state}. "
            f"Respond in a way that fits this state naturally."
        )

        if current_state == "idea_phase":
            parts.append(
                "This thread is in the idea phase. "
                "Help move it forward by offering options, asking a narrowing question, "
                "or adding a fresh twist."
            )

        elif current_state == "planning_phase":
            parts.append(
                "This thread is in the planning phase. "
                "Help move it forward by suggesting steps, choices, or a concrete next move."
            )

    if conversation_is_looping(recent_messages):
        parts.append(
            "The conversation is becoming repetitive. "
            "Do not reply with another simple confirmation, promise, tease, or sign-off. "
            "Move it forward with one fresh idea, one concrete suggestion, or one focused question."
        )

    if sender_name:
        parts.append(
            f"The current sender is {sender_name}. "
            "Keep the reply natural and personal to that sender."
        )

    return "\n".join(parts).strip()


def build_retry_guidance() -> str:
    return (
        "Your previous draft was too passive, repetitive, or low-information. "
        "Rewrite it so it clearly advances the conversation. "
        "The new reply must include at least one of the following: "
        "a specific question, a concrete next step, a clear option, or a fresh idea. "
        "Do not simply confirm availability or mirror the other person's tone. "
        "Stay fully in character and keep it natural."
    )
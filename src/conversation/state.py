from typing import Literal

ThreadState = Literal["opening", "idea_phase", "planning_phase", "closing"]


def detect_thread_state(messages: list[str]) -> ThreadState:
    joined = " ".join(m.lower() for m in messages[-6:])

    closing_signals = [
        "talk soon",
        "take care",
        "bye",
        "goodnight",
        "catch you later",
    ]
    planning_signals = [
        "plan",
        "step",
        "which",
        "how",
        "when",
        "option",
        "schedule",
        "next",
    ]
    idea_signals = [
        "idea",
        "what if",
        "maybe",
        "could",
        "imagine",
        "prank",
        "twist",
    ]

    if any(signal in joined for signal in closing_signals):
        return "closing"
    if any(signal in joined for signal in planning_signals):
        return "planning_phase"
    if any(signal in joined for signal in idea_signals):
        return "idea_phase"
    return "opening"
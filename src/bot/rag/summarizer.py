from __future__ import annotations
from typing import List
from bot.config import AppConfig
from bot.llm.ollama import generate

_SUMMARY_SYS = (
    "You are a compression tool. Summarize the following chat turns into a compact, factual note. "
    "Keep it neutral, actionable, and under the requested word limit. No extra commentary."
)

def summarize_chunk(app_cfg: AppConfig, system_template_path: str, turns: List[tuple[str, str]], max_words: int) -> str:
    """
    turns: list of (role, text) where role in {'user','assistant'}
    """
    # Build a tiny prompt with the recent conversation
    lines = []
    for role, text in turns:
        lines.append(f"{role.title()}: {text.strip()}")
    convo = "\n".join(lines)

    prompt = (
        f"{_SUMMARY_SYS}\n\n"
        f"Max words: {max_words}\n\n"
        f"Conversation:\n{convo}\n\n"
        f"Now produce one concise paragraph capturing key facts/preferences/decisions."
    )
    # We reuse the same generate() but pass the persona system; the summary system text
    # is embedded in the user prompt to keep Step 4 small.
    summary = generate(prompt, app_cfg, system_template_path)
    return summary.strip()

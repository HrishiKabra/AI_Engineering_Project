"""Input guardrails: unsafe-request refusal, length cap, prompt-injection scrubbing.

Adapted from the v1 notebook. Scope enforcement (is this an F1 question?) is the
router node's job via LLM classification; here we only do cheap, deterministic
input hygiene. The incident text a user pastes is untrusted, so retrieved-context
injection scrubbing happens before anything reaches the generator.
"""

from __future__ import annotations

import re

MAX_INPUT_CHARS = 2000

_UNSAFE_TERMS = [
    "how to build a bomb",
    "make a weapon",
    "how to make a weapon",
]

_INJECTION_RE = re.compile(
    r"(ignore (all )?previous|disregard (the )?above|system prompt|you are chatgpt|"
    r"developer message|new instructions:|act as|jailbreak)",
    re.IGNORECASE,
)


def guardrail_check_input(user_input: str) -> str | None:
    """Return a refusal message if the input is unsafe/too long, else None."""
    text = (user_input or "").lower().strip()
    if not text:
        return "Please enter a question about an F1 rule or penalty."
    if len(text) > MAX_INPUT_CHARS:
        return "That question is too long for this demo — please shorten it."
    for term in _UNSAFE_TERMS:
        if term in text:
            return "I can't help with that request."
    return None


def strip_prompt_injection(text: str) -> str:
    """Drop instruction-like lines from untrusted/retrieved text."""
    cleaned = [ln for ln in (text or "").splitlines() if not _INJECTION_RE.search(ln)]
    return "\n".join(cleaned)

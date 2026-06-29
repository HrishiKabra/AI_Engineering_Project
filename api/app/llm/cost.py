"""Token pricing and cost computation (USD per token)."""

from __future__ import annotations

# (prompt_per_token, completion_per_token) in USD. Update as pricing changes.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4o": (2.50 / 1_000_000, 10.0 / 1_000_000),
    "text-embedding-3-small": (0.02 / 1_000_000, 0.0),
    "text-embedding-3-large": (0.13 / 1_000_000, 0.0),
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int = 0) -> float:
    p, c = PRICES.get(model, (0.0, 0.0))
    return prompt_tokens * p + completion_tokens * c


def total_cost(usage: dict) -> float:
    """Sum chat + embedding cost from an accumulated usage dict."""
    chat = cost_usd(
        usage.get("chat_model", ""),
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
    )
    embed = cost_usd(usage.get("embed_model_name", ""), usage.get("embed_tokens", 0), 0)
    return round(chat + embed, 6)

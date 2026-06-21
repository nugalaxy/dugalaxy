"""Estimate tokens and cost before a run; show estimate and require confirmation for paid runs.

Estimates are honest and approximate: token counts use a simple chars/4 heuristic,
and prices come from a best-effort table that providers can and do change. The
config can override prices, and unknown models are flagged ``priced=False`` rather
than silently treated as free. Ollama runs are free.
"""

import math
from dataclasses import dataclass

from dugalaxy.config.schema import Config
from dugalaxy.template.errors import DugalaxyError

# Best-effort USD prices per 1k tokens, (input, output). Providers change prices and
# add models often, so this is a convenience, not a contract: a missing model is
# flagged priced=False (cost shown as 0 but not trusted), and any value here can be
# overridden in config. Anthropic prices are authoritative; the rest are best-effort
# public rates as of 2026-06 — verify against the provider before relying on them.
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4.1": (0.0020, 0.0080),
    "gpt-4.1-mini": (0.00040, 0.00160),
    # Google Gemini (reached via the openai_compatible adapter)
    "gemini-2.5-pro": (0.00125, 0.0100),
    "gemini-2.5-flash": (0.00030, 0.00250),
    "gemini-2.5-flash-lite": (0.00010, 0.00040),
    "gemini-1.5-flash": (0.000075, 0.00030),
    # Anthropic (authoritative)
    "claude-opus-4-8": (0.0050, 0.0250),
    "claude-sonnet-4-6": (0.0030, 0.0150),
    "claude-haiku-4-5": (0.0010, 0.0050),
    "claude-3-5-haiku-latest": (0.00080, 0.00400),
    "claude-3-5-sonnet-latest": (0.00300, 0.01500),
    # DeepSeek
    "deepseek-chat": (0.00027, 0.00110),
}


class CostCapExceededError(DugalaxyError):
    """The estimated run cost exceeds the configured cap."""


@dataclass(frozen=True)
class CostEstimate:
    """A pre-run cost estimate for the whole run."""

    n: int
    total_input_tokens: int
    total_output_tokens: int
    price_per_1k_input: float
    price_per_1k_output: float
    estimated_cost_usd: float
    free: bool  # local/no-charge provider (Ollama)
    priced: bool  # False => pricing unknown; cost shown as 0 but not trustworthy


def estimate_tokens(text: str) -> int:
    """Roughly estimate token count from character length (~4 chars/token)."""
    return max(1, math.ceil(len(text) / 4))


def resolve_pricing(provider: str, model: str, config: Config) -> tuple[float, float, bool]:
    """Return ``(price_in, price_out, priced)`` per 1k tokens for *model*.

    Order: Ollama is free; an explicit config override wins; then the built-in
    table; otherwise pricing is unknown (``priced=False``).
    """
    if provider == "ollama":
        return (0.0, 0.0, True)
    if config.price_per_1k_input is not None and config.price_per_1k_output is not None:
        return (config.price_per_1k_input, config.price_per_1k_output, True)
    if model in DEFAULT_PRICING:
        price_in, price_out = DEFAULT_PRICING[model]
        return (price_in, price_out, True)
    return (0.0, 0.0, False)


def estimate_run_cost(
    *,
    n: int,
    input_tokens_per_sample: int,
    output_tokens_per_sample: int,
    price_per_1k_input: float,
    price_per_1k_output: float,
    priced: bool,
    free: bool,
) -> CostEstimate:
    """Compute the total estimated cost across *n* samples."""
    total_input = input_tokens_per_sample * n
    total_output = output_tokens_per_sample * n
    cost = (total_input / 1000) * price_per_1k_input + (total_output / 1000) * price_per_1k_output
    return CostEstimate(
        n=n,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        price_per_1k_input=price_per_1k_input,
        price_per_1k_output=price_per_1k_output,
        estimated_cost_usd=round(cost, 6),
        free=free,
        priced=priced,
    )


def enforce_cap(estimate: CostEstimate, cap_usd: float) -> None:
    """Raise :class:`CostCapExceededError` if the estimate exceeds *cap_usd*.

    Free runs always pass. An unknown-price run cannot be checked meaningfully, so
    it passes here — callers should surface the ``priced=False`` flag to the user.
    """
    if estimate.free or not estimate.priced:
        return
    if estimate.estimated_cost_usd > cap_usd:
        raise CostCapExceededError(
            f"Estimated cost ${estimate.estimated_cost_usd:.4f} exceeds the cap "
            f"${cap_usd:.2f}. Raise cost_cap_usd, lower n, or use a cheaper model."
        )

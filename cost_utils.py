"""Shared cost calculation utilities used across all Grok response paths."""

import logging

from config import (
    GROK_IMAGE_OUTPUT_COST,
    GROK_TEXT_CACHED_COST,
    GROK_TEXT_INPUT_COST,
    GROK_TEXT_OUTPUT_COST,
    GROK_TOOL_COST,
    GROK_VISION_INPUT_COST,
    GROK_VISION_OUTPUT_COST,
)


logger = logging.getLogger('GrokBot')


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int,
                   cached_tokens: int = 0, tool_invocations: int = 0,
                   has_images: bool = False) -> dict:
    """Calculate cost breakdown for a Grok API call.

    Returns a dict with individual cost components and a total.
    Current Grok chat models bill image tokens as regular input, so vision
    no longer requires a separate model slug.
    """
    is_vision = has_images or 'vision' in model.lower()
    input_rate = GROK_VISION_INPUT_COST if is_vision else GROK_TEXT_INPUT_COST
    output_rate = GROK_VISION_OUTPUT_COST if is_vision else GROK_TEXT_OUTPUT_COST
    uncached = max(prompt_tokens - cached_tokens, 0)
    input_cost = (
        (uncached / 1_000_000) * input_rate
        + (cached_tokens / 1_000_000) * GROK_TEXT_CACHED_COST
    )
    output_cost = (completion_tokens / 1_000_000) * output_rate

    tool_cost = (tool_invocations / 1000) * GROK_TOOL_COST if tool_invocations > 0 else 0
    total = input_cost + output_cost + tool_cost
    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'tool_cost': tool_cost,
        'total': total,
        'is_vision': is_vision,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'tool_invocations': tool_invocations,
    }


def format_cost(model: str, prompt_tokens: int, completion_tokens: int,
                cached_tokens: int = 0, tool_invocations: int = 0,
                has_images: bool = False) -> str:
    """Format cost breakdown as a human-readable string for embed footers."""
    cost = calculate_cost(model, prompt_tokens, completion_tokens,
                          cached_tokens, tool_invocations, has_images=has_images)

    parts = [f"💵 ${cost['total']:.6f}"]

    indicators = []
    if cost['is_vision']:
        vision_total = cost['input_cost'] + cost['output_cost']
        indicators.append(f"👁️ ${vision_total:.6f} vision")
    if cost['tool_cost'] > 0:
        indicators.append(f"🔧 ${cost['tool_cost']:.6f} tools ({tool_invocations})")
    if indicators:
        parts.append(f" ({', '.join(indicators)})")

    parts.append(f" • {prompt_tokens} in / {completion_tokens} out")
    return ''.join(parts)


def format_image_cost() -> str:
    """Format image generation cost string."""
    return f"${GROK_IMAGE_OUTPUT_COST:.2f} (est.)"

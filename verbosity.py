"""Per-channel verbosity control for Grok responses.

Natural-language triggers like "be more concise" or "give me more detail"
adjust the verbosity level for the current channel.  The setting is stored
alongside persona data in the persona store and injected into the Grok
system prompt on every request.
"""

import logging
import re
from typing import Optional

from persona_manager import get_active_verbosity, set_active_verbosity


logger = logging.getLogger('GrokBot')

# ---------------------------------------------------------------------------
# Verbosity levels and their system-prompt modifiers
# ---------------------------------------------------------------------------

VERBOSITY_LEVELS = frozenset({'terse', 'balanced', 'verbose'})
DEFAULT_VERBOSITY = 'balanced'

VERBOSITY_MODIFIERS: dict[str, str] = {
    'terse': (
        "RESPONSE STYLE: Be extremely concise. Answer in 1-2 short sentences. "
        "Use bullet points only when absolutely necessary. Get straight to "
        "the point — no preamble, no fluff."
    ),
    'balanced': (
        "RESPONSE STYLE: Keep responses moderately detailed. Provide enough "
        "context to be useful without being verbose. Use paragraphs and "
        "formatting when it improves clarity."
    ),
    'verbose': (
        "RESPONSE STYLE: Be thorough and detailed. Include examples, "
        "explanations, and relevant context. Use rich formatting, sections, "
        "and break down complex topics. Don't hold back on detail — the "
        "user wants depth."
    ),
}

# ---------------------------------------------------------------------------
# Natural-language detection
# ---------------------------------------------------------------------------

_TERSE_PATTERNS = [
    re.compile(p) for p in [
        r'\b(be|keep|make)\s*(it|your\s*responses?|your\s*answers?|'
        r'the\s*conversation)\s*(more\s*)?'
        r'(concise|brief|short|terse|succinct|to\s*the\s*point)\b',
        r'\bstop\s*(rambling|being\s*(wordy|verbose))\b',
        r'\bdont?\s*ramble\b',
        r'\b(less|shorter)\s*(verbose|wordy|detailed|chatty|answers?|responses?)\b',
        r'\btone\s*it\s*down\b',
        r'\btoo\s*(verbose|wordy|long|chatty)\b',
    ]
]

_VERBOSE_PATTERNS = [
    re.compile(p) for p in [
        r'\b(be|give\s*me|provide)\s*(more\s*)?'
        r'(verbose|detailed|thorough|comprehensive|in[- ]?depth|elaborate)\b',
        r'\b(explain|go)\s*(more|deeper|into\s*(more\s*)?(detail|depth))\b',
        r'\bexpand\s*(on\s*that|more)\b',
        r'\b(dont?\s*be\s*so\s*(terse|brief|short))\b',
        r'\bmore\s*(detail|context|explanation|elaboration)\b',
    ]
]

_BALANCED_PATTERNS = [
    re.compile(p) for p in [
        r'\b(be|keep)\s*(it|your\s*responses?)\s*'
        r'(normal|balanced|moderate|default)\b',
        r'\breset\s*(your|the)\s*(verbosity|style|tone)\b',
    ]
]

VERBOSITY_LABELS = {
    'terse': "🎯 Terse — I'll keep it extremely concise.",
    'balanced': "⚖️ Balanced — back to normal detail.",
    'verbose': "📚 Verbose — I'll be thorough and detailed.",
}


def detect_verbosity_request(prompt: str) -> Optional[str]:
    """Return 'terse', 'verbose', 'balanced', or None."""
    text = prompt.lower().strip()

    for pat in _TERSE_PATTERNS:
        if pat.search(text):
            return 'terse'

    for pat in _VERBOSE_PATTERNS:
        if pat.search(text):
            return 'verbose'

    for pat in _BALANCED_PATTERNS:
        if pat.search(text):
            return 'balanced'

    return None


def verbosity_prompt_modifier(level: str) -> str:
    """Return the system-prompt snippet for a given verbosity level."""
    return VERBOSITY_MODIFIERS.get(level, VERBOSITY_MODIFIERS[DEFAULT_VERBOSITY])


def resolve_verbosity(channel_id: int) -> str:
    """Return the active verbosity level for a channel, falling back to default."""
    stored = get_active_verbosity(channel_id)
    if stored and stored in VERBOSITY_LEVELS:
        return stored
    return DEFAULT_VERBOSITY


async def handle_verbosity_request(message, prompt: str) -> bool:
    """Process a verbosity change request. Returns True if handled."""
    level = detect_verbosity_request(prompt)
    if not level:
        return False

    set_active_verbosity(message.channel.id, level)
    await message.reply(
        f"{VERBOSITY_LABELS.get(level, VERBOSITY_LABELS['balanced'])}\n\n"
        f"_This applies to all messages in this channel. "
        f'Say "be more concise" or "give me more detail" to change it._'
    )
    return True

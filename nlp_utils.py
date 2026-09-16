"""Lightweight NLP helpers for intent detection and entity extraction."""

import logging
import re
from functools import lru_cache

import spacy


logger = logging.getLogger('GrokBot')

_nlp_spacy = None


def _get_spacy_model():
    """Lazy-load the spaCy model. Downloads en_core_web_sm if missing."""
    global _nlp_spacy
    if _nlp_spacy is not None:
        return _nlp_spacy

    try:
        _nlp_spacy = spacy.load('en_core_web_sm')
    except OSError:
        logger.info('spaCy en_core_web_sm model not found — downloading now …')
        import subprocess
        subprocess.run(['python', '-m', 'spacy', 'download', 'en_core_web_sm'], check=True)
        _nlp_spacy = spacy.load('en_core_web_sm')

    return _nlp_spacy


INTENT_PATTERNS = {
    'image_generation': [
        r'\b(generate|create|make|draw|paint|sketch|render|illustrate|visualize)\b.*\b(image|picture|art|artwork|illustration|visual)\b',
        r'\b(image|picture|art|artwork|illustration)\b.*\b(of|for|with|showing)\b',
        r'\bshow me (an? )?(image|picture|art)\b',
        r'\b(grok|bot),?\s*(make|create|generate|draw)\b',
    ],
    'discord_history': [
        r'\b(who|what|how many)\b.*\b(talked|said|mentioned|posted|discussed)\b',
        r'\b(summarize|summary|overview)\b.*\b(chat|discord|server|channel|conversation)\b',
        r'\bin (this|the) (server|channel|discord|chat)\b',
        r'\b(we|our|us)\b.*\b(discuss|talk|mention|chat)\b',
    ],
    'general_query': [
        r'\b(what is|who is|how does|why does|when did|where is)\b',
        r'\b(explain|tell me about|describe)\b',
    ]
}


def detect_intent_pattern(text):
    """Lightweight pattern-based intent detection. Returns intent name or None."""
    text_lower = text.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return None


def advanced_nlp_parse(text):
    """Lightweight NLP: spaCy entities + regex intent. Returns dict."""
    nlp = _get_spacy_model()
    doc = nlp(text)
    entities = [(ent.text, ent.label_) for ent in doc.ents]
    topics = [chunk.text for chunk in doc.noun_chunks]
    intent = detect_intent_pattern(text)

    return {
        'entities': entities,
        'topics': topics,
        'intent': intent,
    }

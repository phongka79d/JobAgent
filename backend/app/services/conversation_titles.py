"""Deterministic, provider-free conversation title derivation."""

from app.db.models.profiles import CONVERSATION_TITLE_MAX, NEW_CONVERSATION_TITLE


def derive_conversation_title(message: str) -> str:
    normalized = " ".join(message.split())
    if not normalized:
        return NEW_CONVERSATION_TITLE
    return normalized[:CONVERSATION_TITLE_MAX].rstrip() or NEW_CONVERSATION_TITLE

from app.db.models.profiles import CONVERSATION_TITLE_MAX, NEW_CONVERSATION_TITLE
from app.services.conversation_titles import derive_conversation_title


def test_title_normalizes_whitespace_and_is_bounded() -> None:
    assert derive_conversation_title("  A   normalized\nmessage  ") == (
        "A normalized message"
    )
    assert len(derive_conversation_title("x" * 200)) == CONVERSATION_TITLE_MAX


def test_blank_title_uses_frozen_default() -> None:
    assert derive_conversation_title(" \n\t ") == NEW_CONVERSATION_TITLE

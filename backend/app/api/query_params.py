"""Reusable strict query parameter dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.schemas.chat import ConversationQuery, HistoryQuery


def history_query(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
) -> HistoryQuery:
    try:
        return HistoryQuery(limit=limit, before=before, conversation_id=conversation_id)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def conversation_query(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> ConversationQuery:
    try:
        return ConversationQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def conversation_history_query(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> HistoryQuery:
    try:
        return HistoryQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


__all__ = ["conversation_history_query", "conversation_query", "history_query"]

"""Fake structured-output provider primitives for CV profile extraction tests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class StructuredResponse:
    """One fake strict-schema runnable with recorded request payloads."""

    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = list(responses)
        self.structured_calls: list[list[object]] = []
        self.structured_kwargs: list[dict[str, Any]] = []

    def with_structured_output(self, _schema: object, **kwargs: Any) -> StructuredResponse:
        self.structured_kwargs.append(dict(kwargs))
        return self

    def invoke(self, messages: list[object]) -> object:
        self.structured_calls.append(messages)
        outcome = self.responses.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class StructuredFactory:
    """Injectable ShopAIKey model factory that always returns one fake model."""

    def __init__(self, responses: Sequence[object]) -> None:
        self.model = StructuredResponse(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> StructuredResponse:
        self.calls.append(dict(kwargs))
        return self.model

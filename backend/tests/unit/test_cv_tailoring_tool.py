from __future__ import annotations

from typing import Any, cast

from app.tools.cv_tailoring import build_create_tailored_cv_tool
from langchain_core.utils.function_calling import convert_to_openai_tool


def test_provider_schema_exposes_only_bounded_instruction() -> None:
    tool = build_create_tailored_cv_tool(coordinator=cast(Any, object()))
    provider = convert_to_openai_tool(tool)
    parameters = provider["function"]["parameters"]
    assert set(parameters["properties"]) == {"instruction"}
    assert parameters["properties"]["instruction"]["maxLength"] == 4_000

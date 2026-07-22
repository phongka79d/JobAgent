from __future__ import annotations

import tomllib
from pathlib import Path

RUNTIME_FORBIDDEN = {
    "langchain",
    "mypy",
    "pytest",
    "pytest-asyncio",
    "ruff",
}
EXPECTED_DEV = {
    "mypy",
    "pytest",
    "pytest-asyncio",
    "ruff",
}


def _name(requirement: str) -> str:
    return requirement.split("==", maxsplit=1)[0].strip()


def test_runtime_and_dev_dependencies_are_separated() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = payload["project"]
    runtime = {_name(item) for item in project["dependencies"]}
    dev = {_name(item) for item in project["optional-dependencies"]["dev"]}
    assert runtime.isdisjoint(RUNTIME_FORBIDDEN)
    assert dev == EXPECTED_DEV

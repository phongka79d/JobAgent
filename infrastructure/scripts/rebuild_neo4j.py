#!/usr/bin/env python3
"""Thin host wrapper for the JobAgent Neo4j rebuild owner (help/version only).

Public entrypoint: ``python infrastructure/scripts/rebuild_neo4j.py``

This host script never runs the destructive rebuild. Only ``--help`` /
``-h`` / ``--version`` are allowed. No arguments or any other invocation exits
non-zero, touches no stores, and prints the exact canonical Compose command.

Canonical live execution (choice C) runs inside Compose only:

  docker compose --env-file .env -f infrastructure/docker-compose.yml \\
    exec -T backend python -m app.graph.rebuild
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

# Prefer an installed backend package; fall back to repo layout for local help.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.graph.rebuild_target import (  # noqa: E402
    CANONICAL_COMPOSE_REBUILD_COMMAND,
)

__all__ = ["CANONICAL_COMPOSE_REBUILD_COMMAND", "main"]

_HELP_TEXT = f"""\
usage: python infrastructure/scripts/rebuild_neo4j.py [--help|--version]

Host wrapper is non-destructive only. It does not rebuild Neo4j, open SQLite,
or call ShopAIKey.

Canonical live execution (choice C; repository root; stack up):
  {CANONICAL_COMPOSE_REBUILD_COMMAND}

Destructive authority is limited to JobAgent Candidate, Job, and Skill labels
inside the Compose backend container (APP_ENV=local, NEO4J_URI=bolt://neo4j:7687,
SQLITE_PATH=/data/jobagent.db).
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Allow only help/version; refuse every destructive or no-arg host path."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print(_HELP_TEXT, end="")
        return 0
    if args == ["--version"]:
        print("JobAgent rebuild host wrapper (help/version only; no host rebuild)")
        return 0
    print(
        "Host rebuild is not authorized. Use only the canonical Compose command:\n"
        f"  {CANONICAL_COMPOSE_REBUILD_COMMAND}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

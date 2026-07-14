"""CLI, host-wrapper, and exclusive choice-C target tests for rebuild (03D).

These tests must not open SQLite or Neo4j stores for refusal and help paths.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from app.core.settings import Settings, clear_settings_cache
from app.graph.rebuild import (
    CANONICAL_COMPOSE_REBUILD_COMMAND,
    RebuildError,
    assert_local_compose_neo4j_target,
    build_arg_parser,
    main,
)
from app.graph.rebuild_target import (
    AUTHORIZED_NEO4J_URI,
    AUTHORIZED_SQLITE_PATH,
)
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS, LOCKED_EMBEDDING_MODEL
from pydantic import AnyHttpUrl, SecretStr

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WRAPPER = _REPO_ROOT / "infrastructure" / "scripts" / "rebuild_neo4j.py"


def _settings(
    *,
    uri: str = AUTHORIZED_NEO4J_URI,
    app_env: str = "local",
    sqlite_path: str = AUTHORIZED_SQLITE_PATH,
) -> Settings:
    return Settings(
        APP_ENV=app_env,
        FRONTEND_ORIGIN="http://127.0.0.1:5173",
        SQLITE_PATH=sqlite_path,
        FILES_DIR="files",
        NEO4J_URI=uri,
        NEO4J_USER="neo4j",
        NEO4J_PASSWORD=SecretStr("unit-test-neo4j-password-NOT-A-REAL-SECRET"),
        SHOPAIKEY_BASE_URL=AnyHttpUrl("https://example.test/v1"),
        SHOPAIKEY_API_KEY=SecretStr("unit-test-shopaikey-not-real"),
        EMBEDDING_MODEL=LOCKED_EMBEDDING_MODEL,
        EMBEDDING_DIMENSIONS=LOCKED_EMBEDDING_DIMENSIONS,
    )


def _load_wrapper_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "rebuild_neo4j_host_wrapper",
        _WRAPPER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_is_non_destructive_and_documents_compose_command() -> None:
    parser = build_arg_parser()
    help_text = parser.format_help()
    assert CANONICAL_COMPOSE_REBUILD_COMMAND in help_text
    assert "ShopAIKey" in help_text or "provider" in help_text.lower()
    assert "Candidate" in help_text
    assert "Job" in help_text
    assert "Skill" in help_text
    assert "bolt://neo4j:7687" in help_text
    assert "/data/jobagent.db" in help_text
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_main_help_exit_zero_no_stores() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_assert_local_target_accepts_exact_compose_contract() -> None:
    assert_local_compose_neo4j_target(_settings())


def test_assert_local_target_refuses_remote() -> None:
    with pytest.raises(RebuildError) as exc:
        assert_local_compose_neo4j_target(
            _settings(uri="bolt://production.example:7687")
        )
    assert exc.value.code == "REBUILD_TARGET_REFUSED"


def test_assert_local_target_refuses_loopback_host() -> None:
    for uri in (
        "bolt://localhost:7687",
        "bolt://127.0.0.1:7687",
    ):
        with pytest.raises(RebuildError) as exc:
            assert_local_compose_neo4j_target(_settings(uri=uri))
        assert exc.value.code == "REBUILD_TARGET_REFUSED"


def test_assert_local_target_refuses_wrong_port() -> None:
    with pytest.raises(RebuildError) as exc:
        assert_local_compose_neo4j_target(_settings(uri="bolt://neo4j:7688"))
    assert exc.value.code == "REBUILD_TARGET_REFUSED"


def test_assert_local_target_refuses_wrong_sqlite_path() -> None:
    with pytest.raises(RebuildError) as exc:
        assert_local_compose_neo4j_target(
            _settings(sqlite_path=":memory:")
        )
    assert exc.value.code == "REBUILD_TARGET_REFUSED"
    with pytest.raises(RebuildError) as exc2:
        assert_local_compose_neo4j_target(
            _settings(sqlite_path="/tmp/other.db")
        )
    assert exc2.value.code == "REBUILD_TARGET_REFUSED"


def test_assert_local_target_refuses_non_local_app_env() -> None:
    with pytest.raises(RebuildError) as exc:
        assert_local_compose_neo4j_target(_settings(app_env="production"))
    assert exc.value.code == "REBUILD_TARGET_REFUSED"
    with pytest.raises(RebuildError) as exc2:
        assert_local_compose_neo4j_target(_settings(app_env="test"))
    assert exc2.value.code == "REBUILD_TARGET_REFUSED"


def test_host_wrapper_help_exits_zero_and_documents_compose() -> None:
    wrapper = _load_wrapper_module()
    main_fn = getattr(wrapper, "main")
    code = main_fn(["--help"])
    assert code == 0
    code_v = main_fn(["--version"])
    assert code_v == 0


def test_host_wrapper_no_arg_refuses_without_store_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-arg host invocation must exit non-zero and never open stores."""
    called: list[str] = []

    def _mark(name: str) -> None:
        called.append(name)

    # Guard application rebuild/driver entrypoints if wrongly imported later.
    import app.graph.rebuild as rebuild_public

    monkeypatch.setattr(
        rebuild_public,
        "main",
        lambda *_a, **_k: (_mark("rebuild.main") or 0),
    )
    monkeypatch.setattr(
        rebuild_public,
        "rebuild_graph",
        lambda *_a, **_k: (_mark("rebuild_graph") or None),
    )

    wrapper = _load_wrapper_module()
    main_fn = getattr(wrapper, "main")
    code = main_fn([])
    assert code == 1
    assert called == []
    # Source must not delegate to the application main entry.
    source = _WRAPPER.read_text(encoding="utf-8")
    assert "app.graph.rebuild import" not in source
    assert "raise SystemExit(main())" in source or "SystemExit(main())" in source
    assert "from app.graph.rebuild_target import" in source


def test_host_wrapper_subprocess_no_arg_prints_canonical_and_exits_nonzero() -> None:
    proc = subprocess.run(
        [sys.executable, str(_WRAPPER)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert CANONICAL_COMPOSE_REBUILD_COMMAND in combined
    # Must not look like a successful rebuild summary.
    assert "Neo4j rebuild complete" not in combined


def test_host_wrapper_subprocess_help_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(_WRAPPER), "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0
    assert CANONICAL_COMPOSE_REBUILD_COMMAND in (proc.stdout or "")


def test_host_wrapper_refuses_bogus_args() -> None:
    wrapper = _load_wrapper_module()
    main_fn = getattr(wrapper, "main")
    assert main_fn(["--force"]) == 1
    assert main_fn(["rebuild"]) == 1


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()

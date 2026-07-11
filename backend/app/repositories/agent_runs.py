"""Durable Agent run lifecycle and request-idempotency repository.

Caller owns the ``AsyncSession`` transaction: methods flush only and never
commit or roll back. One durable run per user-turn message; the run primary
key is the stable LangGraph ``thread_id``. Turn and resume idempotency keys
resolve to the existing run outcome without repeating writes.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Final
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_uuid, utc_now
from app.db.enums import AgentRunState
from app.db.models.conversation import AgentRun, ChatMessage

_MAX_IDEMPOTENCY_KEY_LEN: Final[int] = 128
_MAX_ERROR_LEN: Final[int] = 1024
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# Explicit finite state machine. Terminal states reject further transitions.
_ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    AgentRunState.PENDING.value: frozenset(
        {
            AgentRunState.RUNNING.value,
            AgentRunState.FAILED.value,
        }
    ),
    AgentRunState.RUNNING.value: frozenset(
        {
            AgentRunState.INTERRUPTED.value,
            AgentRunState.COMPLETED.value,
            AgentRunState.FAILED.value,
        }
    ),
    AgentRunState.INTERRUPTED.value: frozenset(
        {
            AgentRunState.RUNNING.value,
            AgentRunState.FAILED.value,
        }
    ),
    AgentRunState.COMPLETED.value: frozenset(),
    AgentRunState.FAILED.value: frozenset(),
}

_TERMINAL_STATES: Final[frozenset[str]] = frozenset(
    {
        AgentRunState.COMPLETED.value,
        AgentRunState.FAILED.value,
    }
)

_PATH_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_AUTH_SCHEME_RE = re.compile(
    r"^(?:Basic|Bearer|Digest|Token|Negotiate|NTLM)\s+\S+",
    re.IGNORECASE,
)
_URI_USERINFO_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#\"']*:[^/\s?#\"']*@",
)
_SECRET_VALUE_MARKERS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


class AgentRunRepositoryError(Exception):
    """Agent run operation failed without disclosing secret values."""


class AgentRunNotFoundError(AgentRunRepositoryError):
    """No agent run exists for the requested identity."""


class AgentRunStateError(AgentRunRepositoryError):
    """Requested state transition is not allowed for the current run state."""


class AgentRunDuplicateError(AgentRunRepositoryError):
    """Reserved for unresolved uniqueness conflicts.

    Durable turn-key races resolve to the existing run via conflict-safe insert
    and must not surface this error to services.
    """


class AgentRunValidationError(AgentRunRepositoryError):
    """Identity, key, or error payload failed closed validation."""


def langgraph_thread_id(run: AgentRun) -> str:
    """Stable LangGraph thread identity for a durable application run."""
    return str(run.id)


def _string_looks_like_path(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    if "file:" in lower:
        return True
    if _PATH_DRIVE_RE.match(stripped):
        return True
    if stripped.startswith("\\\\") or stripped.startswith("//"):
        return True
    if stripped.startswith("/"):
        return True
    if stripped.startswith("./") or stripped.startswith("../"):
        return True
    if "\\" in stripped:
        return True
    return False


def _string_looks_like_secret(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    if _AUTH_SCHEME_RE.match(stripped):
        return True
    if _URI_USERINFO_RE.search(stripped):
        return True
    upper = value.upper()
    for marker in _SECRET_VALUE_MARKERS:
        if marker in upper:
            return True
    return False


def sanitize_run_error(message: str | None) -> str | None:
    """Normalize a run failure string for durable storage.

    Short, whitespace-collapsed text only. Path/secret-shaped values collapse
    to a generic code so raw material never lands in ``agent_runs.error``.
    """
    if message is None:
        return None
    if not isinstance(message, str):
        raise AgentRunValidationError("invalid error message")
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > _MAX_ERROR_LEN:
        cleaned = cleaned[:_MAX_ERROR_LEN]
    if _string_looks_like_path(cleaned) or _string_looks_like_secret(cleaned):
        return "run_failed"
    return cleaned


def _validate_idempotency_key(key: str, *, name: str) -> str:
    if not isinstance(key, str):
        raise AgentRunValidationError(f"invalid {name}")
    cleaned = key.strip()
    if not cleaned or len(cleaned) > _MAX_IDEMPOTENCY_KEY_LEN:
        raise AgentRunValidationError(f"invalid {name}")
    if not _IDEMPOTENCY_KEY_RE.fullmatch(cleaned):
        raise AgentRunValidationError(f"invalid {name}")
    return cleaned


def _validate_uuid(value: UUID, *, name: str) -> UUID:
    if not isinstance(value, UUID):
        raise AgentRunValidationError(f"invalid {name}")
    return value


def _normalize_state(state: str | AgentRunState) -> str:
    if isinstance(state, AgentRunState):
        return state.value
    if not isinstance(state, str):
        raise AgentRunValidationError("invalid state")
    normalized = state.strip().lower()
    allowed = {s.value for s in AgentRunState}
    if normalized not in allowed:
        raise AgentRunValidationError("invalid state")
    return normalized


class AgentRunRepository:
    """Narrow Agent-run lifecycle operations on a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, run_id: UUID) -> AgentRun | None:
        """Load one durable run by primary key, or None."""
        run_id = _validate_uuid(run_id, name="run_id")
        return await self._session.get(AgentRun, run_id)

    async def get_by_message_id(self, message_id: UUID) -> AgentRun | None:
        """Load the single run for a user-turn message, or None."""
        message_id = _validate_uuid(message_id, name="message_id")
        result = await self._session.execute(
            select(AgentRun).where(AgentRun.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_by_turn_idempotency_key(
        self,
        turn_idempotency_key: str,
    ) -> AgentRun | None:
        """Resolve a durable turn request key to its existing run, or None."""
        key = _validate_idempotency_key(
            turn_idempotency_key, name="turn_idempotency_key"
        )
        result = await self._session.execute(
            select(AgentRun).where(AgentRun.turn_idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def create_for_turn(
        self,
        *,
        message_id: UUID,
        turn_idempotency_key: str,
    ) -> AgentRun:
        """Create one pending run for a persisted user turn, or reuse existing.

        Idempotent on ``turn_idempotency_key`` and on ``message_id`` (at most
        one run per user message). Concurrent duplicate turn keys resolve via
        SQLite ``INSERT … ON CONFLICT DO NOTHING`` then select so the service
        never sees a retry/duplicate error. Does not append messages, commit,
        or start graph execution. Returns the durable run whose ``id`` is the
        LangGraph thread identity.
        """
        message_id = _validate_uuid(message_id, name="message_id")
        key = _validate_idempotency_key(
            turn_idempotency_key, name="turn_idempotency_key"
        )

        by_key = await self.get_by_turn_idempotency_key(key)
        if by_key is not None:
            return by_key

        by_message = await self.get_by_message_id(message_id)
        if by_message is not None:
            # One run per message: return existing without a second write.
            return by_message

        message = await self._session.get(ChatMessage, message_id)
        if message is None:
            raise AgentRunValidationError("message_id not found")

        # Core insert with explicit timestamps (Python column defaults are
        # ORM-instance only). ON CONFLICT avoids IntegrityError on races for
        # turn_idempotency_key or message_id uniqueness.
        now = utc_now()
        stmt = (
            sqlite_insert(AgentRun)
            .values(
                id=new_uuid(),
                message_id=message_id,
                state=AgentRunState.PENDING.value,
                pending_approval=False,
                error=None,
                turn_idempotency_key=key,
                resume_idempotency_key=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

        resolved = await self.get_by_turn_idempotency_key(key)
        if resolved is not None:
            return resolved

        resolved = await self.get_by_message_id(message_id)
        if resolved is not None:
            return resolved

        # Should not occur after a successful conflict-safe create on a healthy
        # schema; surface without inventing a second durable run.
        raise AgentRunRepositoryError(
            "agent run missing after conflict-safe create"
        )

    async def transition(
        self,
        run_id: UUID,
        *,
        to_state: str | AgentRunState,
        pending_approval: bool | None = None,
        error: str | None = None,
        expected_states: Collection[str | AgentRunState] | None = None,
    ) -> AgentRun:
        """Apply a validated state transition. Does not commit.

        Rejects invalid or stale transitions. Interrupted runs keep a
        resumable outcome when a non-resume transition is refused.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            raise AgentRunNotFoundError("agent run not found")

        target = _normalize_state(to_state)
        current = run.state

        if expected_states is not None:
            allowed_from = {_normalize_state(s) for s in expected_states}
            if current not in allowed_from:
                raise AgentRunStateError("stale state transition")

        if target == current:
            # No-op same-state is not a progress write; reject as stale to
            # force explicit resume-key handling for interrupted replays.
            raise AgentRunStateError("invalid state transition")

        allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise AgentRunStateError("invalid state transition")

        if target == AgentRunState.INTERRUPTED.value:
            run.state = target
            run.pending_approval = True if pending_approval is None else bool(
                pending_approval
            )
            run.error = None
            # Clear prior resume claim so a later interrupt cycle can claim a
            # new resume key; same-key replay after success still hits the
            # apply_resume early return while the claim remains set.
            run.resume_idempotency_key = None
        elif target == AgentRunState.COMPLETED.value:
            run.state = target
            run.pending_approval = False
            run.error = None
        elif target == AgentRunState.FAILED.value:
            run.state = target
            run.pending_approval = False
            run.error = sanitize_run_error(error)
        elif target == AgentRunState.RUNNING.value:
            run.state = target
            if pending_approval is not None:
                run.pending_approval = bool(pending_approval)
            else:
                run.pending_approval = False
            # Clear prior non-terminal error noise when re-entering running.
            run.error = None
        else:
            raise AgentRunStateError("invalid state transition")

        await self._session.flush()
        return run

    async def apply_resume(
        self,
        run_id: UUID,
        *,
        resume_idempotency_key: str,
    ) -> AgentRun:
        """Resume an interrupted run, or return existing on duplicate key.

        Same ``resume_idempotency_key`` for the run is a durable no-op (no
        second resume write). Competing same-key resumes use a conditional
        state update so exactly one writer claims the interrupted → running
        transition; losers re-select and return the same outcome. A new key is
        accepted only while the run is ``interrupted``. Does not commit.
        """
        run_id = _validate_uuid(run_id, name="run_id")
        key = _validate_idempotency_key(
            resume_idempotency_key, name="resume_idempotency_key"
        )
        run = await self.get_by_id(run_id)
        if run is None:
            raise AgentRunNotFoundError("agent run not found")

        if run.resume_idempotency_key is not None and run.resume_idempotency_key == key:
            # Replay: return the durable outcome without re-applying resume.
            return run

        if run.state != AgentRunState.INTERRUPTED.value:
            raise AgentRunStateError("invalid state transition")

        # Atomic claim: only one concurrent writer can leave interrupted with
        # this key (or unclaimed). Rowcount 0 means a peer already claimed or
        # the state changed; resolve by re-select without a second transition.
        now = utc_now()
        claim = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.state == AgentRunState.INTERRUPTED.value,
                or_(
                    AgentRun.resume_idempotency_key.is_(None),
                    AgentRun.resume_idempotency_key == key,
                ),
            )
            .values(
                state=AgentRunState.RUNNING.value,
                pending_approval=False,
                error=None,
                resume_idempotency_key=key,
                updated_at=now,
            )
        )
        await self._session.execute(claim)
        # Core UPDATE does not refresh ORM instances; expire so re-select is fresh.
        self._session.expire_all()

        final = await self.get_by_id(run_id)
        if final is None:
            raise AgentRunNotFoundError("agent run not found")

        if (
            final.resume_idempotency_key == key
            and final.state == AgentRunState.RUNNING.value
        ):
            return final

        # Peer applied a different resume or moved state; do not invent a write.
        raise AgentRunStateError("invalid state transition")


    async def mark_running(self, run_id: UUID) -> AgentRun:
        """Move pending run into running. Does not commit."""
        return await self.transition(
            run_id,
            to_state=AgentRunState.RUNNING,
            expected_states={AgentRunState.PENDING},
        )

    async def mark_interrupted(self, run_id: UUID) -> AgentRun:
        """Mark a running run as interrupted with pending approval."""
        return await self.transition(
            run_id,
            to_state=AgentRunState.INTERRUPTED,
            pending_approval=True,
            expected_states={AgentRunState.RUNNING},
        )

    async def mark_completed(self, run_id: UUID) -> AgentRun:
        """Mark a running run completed (terminal)."""
        return await self.transition(
            run_id,
            to_state=AgentRunState.COMPLETED,
            expected_states={AgentRunState.RUNNING},
        )

    async def mark_failed(
        self,
        run_id: UUID,
        *,
        error: str | None = None,
    ) -> AgentRun:
        """Mark a non-terminal run failed with a sanitized error string."""
        run = await self.get_by_id(run_id)
        if run is None:
            raise AgentRunNotFoundError("agent run not found")
        if run.state in _TERMINAL_STATES:
            raise AgentRunStateError("invalid state transition")
        return await self.transition(
            run_id,
            to_state=AgentRunState.FAILED,
            error=error,
            expected_states={
                AgentRunState.PENDING,
                AgentRunState.RUNNING,
                AgentRunState.INTERRUPTED,
            },
        )

    async def count_for_message(self, message_id: UUID) -> int:
        """Return how many runs reference ``message_id`` (expect 0 or 1)."""
        message_id = _validate_uuid(message_id, name="message_id")
        result = await self._session.execute(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.message_id == message_id)
        )
        return int(result.scalar_one())

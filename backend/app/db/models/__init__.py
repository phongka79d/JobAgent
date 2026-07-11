"""Application table models registered on ``Base.metadata``.

Exactly eleven tables. LangGraph checkpoint models are not defined here.
"""

from __future__ import annotations

from app.db.models.attachments import Attachment
from app.db.models.conversation import (
    AgentRun,
    ChatMessage,
    Conversation,
    ToolExecution,
)
from app.db.models.jobs import JobPost
from app.db.models.memory import MemoryFact
from app.db.models.outbox import GraphSyncOutbox
from app.db.models.profile import CandidateProfile, JobPreferences, ProfileDraft

# Stable ordered inventory used by tests and documentation.
APPLICATION_TABLE_NAMES: tuple[str, ...] = (
    "attachments",
    "candidate_profile",
    "profile_drafts",
    "job_preferences",
    "job_posts",
    "conversation",
    "chat_messages",
    "agent_runs",
    "tool_executions",
    "memory_facts",
    "graph_sync_outbox",
)

__all__ = [
    "APPLICATION_TABLE_NAMES",
    "AgentRun",
    "Attachment",
    "CandidateProfile",
    "ChatMessage",
    "Conversation",
    "GraphSyncOutbox",
    "JobPost",
    "JobPreferences",
    "MemoryFact",
    "ProfileDraft",
    "ToolExecution",
]

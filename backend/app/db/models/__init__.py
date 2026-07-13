"""Application ORM models package.

Import model modules so tables register on the shared declarative ``Base``
metadata. Attachment/profile, job_posts, and chat-family tables are defined.
"""

from __future__ import annotations

from app.db.models.attachments import Attachment
from app.db.models.chat import AgentRun, ChatMessage, Conversation, ToolExecution
from app.db.models.jobs import JobPost
from app.db.models.profiles import CandidateProfile, JobPreferences, ProfileDraft

__all__ = [
    "AgentRun",
    "Attachment",
    "CandidateProfile",
    "ChatMessage",
    "Conversation",
    "JobPost",
    "JobPreferences",
    "ProfileDraft",
    "ToolExecution",
]

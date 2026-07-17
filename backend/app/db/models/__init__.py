"""Application ORM models package.

Import model modules so tables register on the shared declarative ``Base``
metadata. Attachment/profile, job_posts, chat-family, chunk, and CV document
tables.
"""

from __future__ import annotations

from app.db.models.attachment_text_chunks import AttachmentTextChunk
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentRun, ChatMessage, Conversation, ToolExecution
from app.db.models.cv_documents import CVDocument, CVDocumentDraft
from app.db.models.jobs import JobPost
from app.db.models.profiles import CandidateProfile, JobPreferences, ProfileDraft

__all__ = [
    "AgentRun",
    "Attachment",
    "AttachmentTextChunk",
    "CVDocument",
    "CVDocumentDraft",
    "CandidateProfile",
    "ChatMessage",
    "Conversation",
    "JobPost",
    "JobPreferences",
    "ProfileDraft",
    "ToolExecution",
]

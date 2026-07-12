"""Public attachment response contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StagedAttachmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    page_count: int
    state: str

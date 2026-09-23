from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CreatePodcastShareRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class PodcastShareData(BaseModel):
    id: UUID
    podcast_version_id: UUID
    recording_id: UUID
    title: str
    url: str
    expires_at: datetime
    revoked_at: datetime | None = None
    access_count: int = Field(ge=0)
    created_at: datetime


class PublicPodcastShareData(BaseModel):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list, max_length=5)
    cover_url: str | None = None
    cover_download_url: str | None = None
    media_url: str
    expires_at: datetime
    duration_ms: int = Field(ge=0)
    render_mode: Literal["narrated", "original_only"]

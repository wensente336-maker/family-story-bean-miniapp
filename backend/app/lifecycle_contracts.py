from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TimelineKind = Literal["recording", "moment", "comic", "podcast"]


class TimelineItemData(BaseModel):
    id: UUID
    kind: TimelineKind
    title: str
    subtitle: str
    status: str
    created_at: datetime
    recording_id: UUID | None = None
    target_path: str
    member_ids: list[UUID] = Field(default_factory=list)


class TimelineData(BaseModel):
    items: list[TimelineItemData]
    total: int


class CreateShareRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class ShareData(BaseModel):
    id: UUID
    creation_id: UUID
    creation_type: Literal["COMIC", "PODCAST"]
    title: str
    url: str
    expires_at: datetime
    revoked_at: datetime | None = None
    access_count: int = 0
    created_at: datetime


class PublicShareData(BaseModel):
    creation_id: UUID
    creation_type: Literal["COMIC", "PODCAST"]
    title: str
    expires_at: datetime
    media_url: str | None = None
    panels: list[dict] = Field(default_factory=list)


class PrivacySettingsData(BaseModel):
    family_id: UUID
    recording_retention_days: int = Field(ge=1, le=30)
    share_default_hours: int = Field(ge=1, le=168)
    sharing_enabled: bool
    updated_at: datetime


class UpdatePrivacySettingsRequest(BaseModel):
    recording_retention_days: int = Field(ge=1, le=30)
    share_default_hours: int = Field(ge=1, le=168)
    sharing_enabled: bool


class DeleteResultData(BaseModel):
    target_id: UUID
    scope: str
    deleted: Literal[True] = True
    object_count: int
    completed_at: datetime


class FamilyMetricsData(BaseModel):
    recordings_total: int
    upload_success_rate: float | None
    analysis_success_rate: float | None
    generation_success_rate: float | None
    processing_p95_seconds: float | None
    deletion_success_rate: float | None
    active_shares: int

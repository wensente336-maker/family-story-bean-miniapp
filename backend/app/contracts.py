from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


T = TypeVar("T")


class ApiMeta(BaseModel):
    request_id: str
    timestamp: datetime


class ApiResponse(BaseModel, Generic[T]):
    ok: Literal[True] = True
    data: T
    meta: ApiMeta


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    ok: Literal[False] = False
    error: ApiErrorDetail
    meta: ApiMeta


class JobStage(StrEnum):
    created = "CREATED"
    uploading = "UPLOADING"
    uploaded = "UPLOADED"
    preprocessing = "PREPROCESSING"
    transcribing = "TRANSCRIBING"
    analyzing = "ANALYZING"
    ready = "READY_FOR_SELECTION"
    generating = "GENERATING"
    completed = "COMPLETED"
    failed = "FAILED"
    cancelled = "CANCELLED"
    deleted = "DELETED"


class FamilySummary(BaseModel):
    id: UUID
    name: str
    member_labels: list[str]


class ProcessingSummary(BaseModel):
    recording_id: UUID
    job_id: UUID
    title: str
    detail: str
    stage: JobStage
    progress: int = Field(ge=0, le=100)


class MomentSummary(BaseModel):
    id: UUID
    recording_id: UUID
    theme: str
    duration_ms: int = Field(gt=0)
    title: str
    quote: str
    color: Literal["sun", "coral", "mint"]


class HomeData(BaseModel):
    family: FamilySummary
    processing: ProcessingSummary | None
    moments: list[MomentSummary]


class SourceSegment(BaseModel):
    transcript_segment_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    quote: str | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> SourceSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class StoryboardCharacter(BaseModel):
    family_member_id: UUID | None = None
    speaker_key: str
    display_name: str


class Storyboard(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    pipeline_version: str
    title: str
    scene: str
    story_type: str
    characters: list[StoryboardCharacter]
    setup: str
    turning_point: str
    ending: str
    highlight_quote: str | None = None
    emotion_curve: list[str]
    source_segments: list[SourceSegment] = Field(min_length=1)
    sensitive_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class JobData(BaseModel):
    id: UUID
    recording_id: UUID
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    retry_count: int = Field(ge=0)
    pipeline_version: str
    error_code: str | None = None
    error_detail: dict[str, Any] = Field(default_factory=dict)
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

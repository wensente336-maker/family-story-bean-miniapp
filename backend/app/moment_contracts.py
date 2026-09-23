from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .contracts import Storyboard


class MomentData(BaseModel):
    id: UUID
    recording_id: UUID
    title: str
    theme: str | None = None
    score: float
    rank: int
    start_ms: int
    end_ms: int
    selection_state: Literal["candidate", "kept", "dismissed"]
    score_breakdown: dict[str, float]
    storyboard: Storyboard
    transcript_revision: int
    edited_by_user: bool
    pipeline_version: str
    created_at: datetime
    updated_at: datetime


class MomentListData(BaseModel):
    recording_id: UUID
    moments: list[MomentData]


class UpdateMomentRequest(BaseModel):
    selection_state: Literal["candidate", "kept", "dismissed"] | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_changes(self):
        if self.selection_state is None and self.start_ms is None and self.end_ms is None:
            raise ValueError("at least one change is required")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("start_ms and end_ms must be supplied together")
        if self.start_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TranscriptWordData(BaseModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TranscriptSegmentData(BaseModel):
    id: UUID
    recording_id: UUID
    family_member_id: UUID | None = None
    speaker_key: str
    start_ms: int
    end_ms: int
    text: str
    original_text: str
    confidence: float | None = None
    words: list[TranscriptWordData] = Field(default_factory=list)
    edited_by_user: bool
    pipeline_version: str
    created_at: datetime
    updated_at: datetime


class SpeakerMappingData(BaseModel):
    speaker_key: str
    family_member_id: UUID | None = None
    display_name: str


class TranscriptFamilyMemberData(BaseModel):
    id: UUID
    nickname: str


class TranscriptData(BaseModel):
    recording_id: UUID
    title: str
    duration_ms: int
    language: str | None = None
    asr_provider: str | None = None
    asr_model: str | None = None
    revision: int
    low_confidence_threshold: float
    speakers: list[SpeakerMappingData]
    family_members: list[TranscriptFamilyMemberData]
    segments: list[TranscriptSegmentData]


class UpdateTranscriptSegmentRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    speaker_key: str | None = Field(default=None, pattern=r"^speaker_[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def at_least_one_change(self):
        if self.text is None and self.speaker_key is None:
            raise ValueError("text or speaker_key is required")
        return self


class UpdateSpeakerMappingRequest(BaseModel):
    family_member_id: UUID | None = None
    display_name: str = Field(min_length=1, max_length=40)


class PlaybackUrlData(BaseModel):
    url: str
    expires_at: int

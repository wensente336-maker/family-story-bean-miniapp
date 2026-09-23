from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .contracts import JobData, JobStage


class CreateRecordingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    original_file_name: str = Field(min_length=1, max_length=255)
    declared_media_type: str | None = Field(default=None, max_length=100)
    declared_size: int = Field(gt=0, le=524288000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_type: Literal[
        "audio_upload", "video_upload", "mobile_recording", "recording_bean"
    ] = "audio_upload"


class CompleteUploadRequest(BaseModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RecordingData(BaseModel):
    id: UUID
    family_id: UUID
    title: str
    original_file_name: str
    media_type: str | None
    file_size: int | None
    duration_ms: int | None
    sha256: str | None
    source_type: Literal[
        "audio_upload", "video_upload", "mobile_recording", "recording_bean"
    ] = "audio_upload"
    status: JobStage
    error_code: str | None = None
    delete_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UploadTargetData(BaseModel):
    method: Literal["PUT"] = "PUT"
    url: str
    expires_at: int
    headers: dict[str, str]


class CreateRecordingData(BaseModel):
    recording: RecordingData
    upload: UploadTargetData


class CompleteUploadData(BaseModel):
    recording: RecordingData
    job: JobData


class UploadReceiptData(BaseModel):
    recording_id: UUID
    bytes_received: int
    sha256: str


class DeleteRecordingData(BaseModel):
    id: UUID
    deleted: Literal[True] = True

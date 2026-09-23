from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class HighlightCoverData(BaseModel):
    id: UUID
    url: str
    thumbnail_url: str
    width: int
    height: int
    sha256: str
    aspect_ratio: Literal['1:1','3:4'] = '1:1'
    layout_version: int = 1
    focal_x: float = .5
    focal_y: float = .5


class HighlightWorkData(BaseModel):
    id: UUID
    source_moment_id: UUID | None = None
    recording_id: UUID
    title: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=1, max_length=500)
    share_allowed: bool = True
    start_ms: int
    end_ms: int
    duration_ms: int
    audio_status: Literal['PENDING','READY','UNAVAILABLE','FAILED']
    audio_url: str | None = None
    cover: HighlightCoverData | None = None
    member_ids: list[UUID] = Field(default_factory=list)
    like_count: int = 0
    comment_count: int = 0
    liked_by_me: bool = False
    can_edit: bool = True
    can_comment: bool = True
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UpdateHighlightWorkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def normalize(self):
        self.title, self.quote = self.title.strip(), self.quote.strip()
        if not self.title or not self.quote:
            raise ValueError('title and quote must not be blank')
        return self


class HighlightShareData(BaseModel):
    id: UUID
    highlight_work_id: UUID
    title: str
    url: str = ''
    expires_at: datetime
    revoked_at: datetime | None = None
    access_count: int = 0
    created_at: datetime


class CreateHighlightShareRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class PublicHighlightData(BaseModel):
    title: str
    quote: str
    duration_ms: int
    audio_url: str
    cover_url: str | None = None
    expires_at: datetime


class HighlightTrashActionData(BaseModel):
    id: UUID
    deleted_at: datetime | None = None


class HighlightReactionData(BaseModel):
    highlight_work_id: UUID
    liked: bool
    like_count: int


class HighlightCommentData(BaseModel):
    id: UUID
    highlight_work_id: UUID
    author_name: str
    body: str
    can_edit: bool = False
    can_delete: bool = False
    created_at: datetime
    updated_at: datetime


class HighlightCommentPageData(BaseModel):
    items: list[HighlightCommentData]
    next_cursor: UUID | None = None


class CreateHighlightCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def normalize(self):
        self.body = self.body.strip()
        if not self.body:
            raise ValueError('comment must not be blank')
        return self


class UpdateHighlightCommentRequest(CreateHighlightCommentRequest):
    pass

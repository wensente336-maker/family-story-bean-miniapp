from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PodcastVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


PODCAST_VERSION_TRANSITIONS: dict[PodcastVersionStatus, set[PodcastVersionStatus]] = {
    PodcastVersionStatus.DRAFT: {PodcastVersionStatus.CONFIRMED},
    PodcastVersionStatus.CONFIRMED: {
        PodcastVersionStatus.DRAFT,
        PodcastVersionStatus.GENERATING,
    },
    PodcastVersionStatus.GENERATING: {
        PodcastVersionStatus.COMPLETED,
        PodcastVersionStatus.FAILED,
    },
    PodcastVersionStatus.COMPLETED: set(),
    PodcastVersionStatus.FAILED: {
        PodcastVersionStatus.DRAFT,
        PodcastVersionStatus.GENERATING,
    },
}


def can_transition_podcast_version(
    current: PodcastVersionStatus, target: PodcastVersionStatus
) -> bool:
    return target in PODCAST_VERSION_TRANSITIONS[current]


class PodcastMaterialData(BaseModel):
    id: UUID
    source_moment_id: UUID | None = None
    source_recording_id: UUID
    source_segment_id: UUID
    family_member_id: UUID | None = None
    speaker_key: str = Field(min_length=1, max_length=80)
    speaker_label: str = Field(min_length=1, max_length=80)
    role: Literal["setup", "highlight", "response", "ending"]
    position: int = Field(ge=1, le=10)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0, le=900_000)
    original_text: str = Field(min_length=1, max_length=4000)
    confirmed_text: str = Field(min_length=1, max_length=4000)
    share_allowed: bool = True

    @model_validator(mode="after")
    def valid_source_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class PodcastMaterialSetData(BaseModel):
    id: UUID
    recording_id: UUID
    status: Literal["DRAFT", "CONFIRMED"]
    revision: int = Field(ge=1)
    schema_version: str
    materials: list[PodcastMaterialData] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_materials(self):
        ids = [item.id for item in self.materials]
        positions = [item.position for item in self.materials]
        if len(set(ids)) != len(ids) or len(set(positions)) != len(positions):
            raise ValueError("materials and positions must be unique")
        if any(item.source_recording_id != self.recording_id for item in self.materials):
            raise ValueError("all materials must belong to the same recording")
        return self


class PodcastMaterialFamilyMemberData(BaseModel):
    id: UUID
    nickname: str


class PodcastMaterialWorkspaceData(BaseModel):
    id: UUID
    project_id: UUID
    podcast_version_id: UUID
    recording_id: UUID
    recording_title: str
    recording_duration_ms: int = Field(gt=0, le=900_000)
    status: Literal["DRAFT", "CONFIRMED"]
    revision: int = Field(ge=1)
    schema_version: str
    transcript_revision: int = Field(ge=0)
    materials: list[PodcastMaterialData] = Field(min_length=1, max_length=10)
    family_members: list[PodcastMaterialFamilyMemberData]
    created_at: datetime
    updated_at: datetime


class UpdatePodcastMaterialItem(BaseModel):
    id: UUID
    family_member_id: UUID | None = None
    speaker_label: str = Field(min_length=1, max_length=80)
    role: Literal["setup", "highlight", "response", "ending"]
    position: int = Field(ge=1, le=10)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0, le=900_000)
    confirmed_text: str = Field(min_length=1, max_length=4000)
    share_allowed: bool = True

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class UpdatePodcastMaterialSetRequest(BaseModel):
    status: Literal["DRAFT", "CONFIRMED"] = "DRAFT"
    materials: list[UpdatePodcastMaterialItem] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_material_set(self):
        ids = [item.id for item in self.materials]
        positions = [item.position for item in self.materials]
        if len(set(ids)) != len(ids) or len(set(positions)) != len(positions):
            raise ValueError("materials and positions must be unique")
        if sorted(positions) != list(range(1, len(positions) + 1)):
            raise ValueError("positions must be contiguous and start at 1")
        return self


class PodcastPlanSegmentData(BaseModel):
    segment_index: int = Field(ge=1)
    kind: Literal["narration", "original"]
    label: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    source_material_ids: list[UUID] = Field(min_length=1, max_length=10)


class PodcastPlanData(BaseModel):
    id: UUID
    material_set_id: UUID
    status: Literal["DRAFT", "CONFIRMED"]
    revision: int = Field(ge=1)
    schema_version: str
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    narrator_voice: str = Field(min_length=1, max_length=120)
    music_style: str = Field(min_length=1, max_length=80)
    narration_style: Literal["warm", "humorous", "growth", "documentary"] = "warm"
    generator_provider: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=120)
    external_share_allowed: bool = True
    safety_checks: dict[str, bool] = Field(default_factory=dict)
    segments: list[PodcastPlanSegmentData] = Field(min_length=3)


class CreatePodcastPlanRequest(BaseModel):
    narration_style: Literal["warm", "humorous", "growth", "documentary"] = "warm"


class PodcastPlanWorkspaceData(BaseModel):
    recording_id: UUID
    recording_title: str
    podcast_version_id: UUID
    material_set_id: UUID
    material_revision: int = Field(ge=1)
    materials: list[PodcastMaterialData] = Field(min_length=1, max_length=10)
    plan: PodcastPlanData


class UpdatePodcastPlanSegment(BaseModel):
    segment_index: int = Field(ge=1)
    kind: Literal["narration", "original"]
    label: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    source_material_ids: list[UUID] = Field(min_length=1, max_length=10)


class UpdatePodcastPlanRequest(BaseModel):
    status: Literal["DRAFT", "CONFIRMED"] = "DRAFT"
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    narrator_voice: str = Field(min_length=1, max_length=120)
    music_style: str = Field(min_length=1, max_length=80)
    segments: list[UpdatePodcastPlanSegment] = Field(min_length=3)

    @model_validator(mode="after")
    def sequential_segments(self):
        indices = [item.segment_index for item in self.segments]
        if indices != list(range(1, len(indices) + 1)):
            raise ValueError("segment indices must be sequential")
        return self


class PodcastNarrationPreviewRequest(BaseModel):
    segment_index: int = Field(ge=1)


class PodcastNarrationPreviewData(BaseModel):
    url: str
    expires_at: int
    provider: str
    voice: str


class PodcastRenderJobData(BaseModel):
    id: UUID
    podcast_version_id: UUID
    status: Literal["CREATED", "GENERATING", "COMPLETED", "FAILED"]
    progress: int = Field(ge=0, le=100)
    retry_count: int = Field(ge=0)
    error_code: str | None = None
    error_detail: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PodcastRenderResultData(BaseModel):
    job: PodcastRenderJobData
    podcast_version_id: UUID
    object_key: str | None = None
    render_metadata: dict = Field(default_factory=dict)


class PodcastRenderPlaybackData(BaseModel):
    url: str
    download_url: str
    expires_at: int
    render_metadata: dict = Field(default_factory=dict)


class PodcastProductCoverData(BaseModel):
    id: UUID
    url: str
    thumbnail_url: str
    media_type: Literal["image/webp"] = "image/webp"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    aspect_ratio: Literal["1:1", "3:4"] = "1:1"
    layout_version: int = 1
    focal_x: float = .5
    focal_y: float = .5


class PodcastProductTagData(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=30)
    kind: Literal["system", "custom"]


class PodcastProductChapterData(BaseModel):
    segment_index: int = Field(ge=1)
    kind: Literal["narration", "original"]
    label: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    source_segment_id: UUID | None = None


class PodcastProductSourceData(BaseModel):
    material_id: UUID
    source_segment_id: UUID
    speaker_label: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confirmed_text: str


class PodcastProductData(BaseModel):
    podcast_version_id: UUID
    recording_id: UUID
    version: int = Field(ge=1)
    status: Literal["COMPLETED"]
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    duration_ms: int = Field(ge=0)
    render_mode: Literal["narrated", "original_only"]
    audio_asset_fingerprint: str
    cover: PodcastProductCoverData | None = None
    tags: list[PodcastProductTagData] = Field(default_factory=list, max_length=5)
    available_tags: list[PodcastProductTagData] = Field(default_factory=list)
    chapters: list[PodcastProductChapterData] = Field(default_factory=list)
    sources: list[PodcastProductSourceData] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    like_count: int = 0
    comment_count: int = 0
    liked_by_me: bool = False
    can_edit: bool = True
    can_comment: bool = True


class PodcastReactionData(BaseModel):
    podcast_version_id: UUID
    liked: bool
    like_count: int


class PodcastCommentData(BaseModel):
    id: UUID
    podcast_version_id: UUID
    author_name: str
    body: str
    can_edit: bool = False
    can_delete: bool = False
    created_at: datetime
    updated_at: datetime


class PodcastCommentPageData(BaseModel):
    items: list[PodcastCommentData]
    next_cursor: UUID | None = None


class CreatePodcastCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def normalize(self):
        self.body = self.body.strip()
        if not self.body:
            raise ValueError("comment must not be blank")
        return self


class UpdatePodcastCommentRequest(CreatePodcastCommentRequest):
    pass


class DeletePodcastProductRequest(BaseModel):
    confirmed: Literal[True]


class PodcastTrashActionData(BaseModel):
    recording_id: UUID
    deleted_at: datetime | None = None


class UpdatePodcastProductRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def normalized_unique_tags(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        normalized = [item.strip() for item in self.tags]
        if any(not item or len(item) > 30 for item in normalized):
            raise ValueError("tags must contain 1 to 30 characters")
        if len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("tags must be unique")
        self.tags = normalized
        return self


class DeletePodcastCoverData(BaseModel):
    deleted: bool


class CoverAssetData(BaseModel):
    id: UUID
    object_key: str = Field(min_length=1, max_length=1024)
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)


class PodcastTagData(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=30)
    kind: Literal["system", "custom"]


class PodcastVersionData(BaseModel):
    id: UUID
    project_id: UUID
    version: int = Field(ge=1)
    status: PodcastVersionStatus
    material_set: PodcastMaterialSetData
    plan: PodcastPlanData | None = None
    cover: CoverAssetData | None = None
    tags: list[PodcastTagData] = Field(default_factory=list, max_length=5)
    object_key: str | None = None
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def state_has_required_artifacts(self):
        if self.status in {
            PodcastVersionStatus.CONFIRMED,
            PodcastVersionStatus.GENERATING,
            PodcastVersionStatus.COMPLETED,
        } and (self.plan is None or self.plan.status != "CONFIRMED"):
            raise ValueError("confirmed and generated versions require a confirmed plan")
        if self.status == PodcastVersionStatus.COMPLETED and not self.object_key:
            raise ValueError("completed versions require an object_key")
        if len({tag.id for tag in self.tags}) != len(self.tags):
            raise ValueError("tags must be unique")
        return self


class CreatePodcastRequest(BaseModel):
    moment_ids: list[UUID] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_moments(self):
        if len(set(self.moment_ids)) != len(self.moment_ids):
            raise ValueError("moment_ids must be unique")
        return self


class RemixPodcastRequest(BaseModel):
    moment_ids: list[UUID] = Field(min_length=1, max_length=3)
    intro: str = Field(min_length=1, max_length=600)
    outro: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def unique_moments(self):
        if len(set(self.moment_ids)) != len(self.moment_ids):
            raise ValueError("moment_ids must be unique")
        return self


class PodcastMomentData(BaseModel):
    id: UUID
    title: str
    theme: str | None = None
    position: int = Field(ge=1, le=3)
    start_ms: int
    end_ms: int


class PodcastSegmentData(BaseModel):
    id: UUID
    segment_index: int = Field(ge=1)
    kind: str
    label: str
    text: str
    source_moment_id: UUID | None = None
    source_segment_id: UUID | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class PodcastData(BaseModel):
    id: UUID
    recording_id: UUID
    title: str
    status: str
    version: int
    pipeline_version: str
    metadata: dict
    moments: list[PodcastMomentData]
    segments: list[PodcastSegmentData]
    created_at: datetime
    updated_at: datetime


class PodcastPlaybackData(BaseModel):
    url: str
    download_url: str
    expires_at: int

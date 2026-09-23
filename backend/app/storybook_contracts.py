from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class StorybookClipData(BaseModel):
    source_segment_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("clip end_ms must be greater than start_ms")
        return self


class StorybookPageData(BaseModel):
    index: int = Field(ge=0)
    type: Literal["cover", "story", "ending"]
    title: str
    narration: str
    panel_index: int | None = Field(default=None, ge=1, le=4)
    panel_version: int | None = Field(default=None, ge=1)
    clip: StorybookClipData | None = None


class StorybookAudioData(BaseModel):
    background_mode: str
    page_turn_mode: str
    narration_mode: str
    highlight_source: str


class StorybookManifestData(BaseModel):
    schema_version: Literal["storybook-manifest-v1"]
    source_comic_id: UUID
    source_comic_version: int = Field(ge=1)
    title: str
    page_count: int = Field(ge=2)
    audio: StorybookAudioData
    pages: list[StorybookPageData] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_page_sequence(self):
        if self.page_count != len(self.pages):
            raise ValueError("page_count must match pages")
        if [page.index for page in self.pages] != list(range(len(self.pages))):
            raise ValueError("page indexes must be contiguous")
        if self.pages[0].type != "cover" or self.pages[-1].type != "ending":
            raise ValueError("manifest must start with cover and end with ending")
        return self


class StorybookVersionSummary(BaseModel):
    version: int = Field(ge=1)
    schema_version: str
    source_comic_version: int = Field(ge=1)
    created_at: datetime


class StorybookData(BaseModel):
    id: UUID
    comic_id: UUID
    recording_id: UUID
    title: str
    status: str
    current_version: int = Field(ge=1)
    schema_version: str
    source_comic_version: int = Field(ge=1)
    manifest: StorybookManifestData
    created_at: datetime
    updated_at: datetime


class StorybookVersionData(BaseModel):
    storybook_id: UUID
    version: int = Field(ge=1)
    schema_version: str
    source_comic_version: int = Field(ge=1)
    manifest: StorybookManifestData
    created_at: datetime


class StorybookAudioClipData(BaseModel):
    page_index: int = Field(ge=0)
    source_segment_id: UUID
    original_start_ms: int = Field(ge=0)
    original_end_ms: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    url: str


class StorybookAudioSessionData(BaseModel):
    storybook_id: UUID
    version: int = Field(ge=1)
    source_recording_id: UUID
    expires_at: int
    clips: list[StorybookAudioClipData]


class StorybookExperienceCueData(BaseModel):
    segment_index: int = Field(ge=1)
    kind: Literal["narration", "original"]
    label: str
    text: str
    page_index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    source_segment_id: UUID | None = None


class StorybookExperienceSceneData(BaseModel):
    page_index: int = Field(ge=0)
    type: Literal["cover", "story", "ending"]
    title: str
    narration: str
    quote: str | None = None
    source_segment_id: UUID | None = None
    speaker_name: str | None = None
    scene_kind: str | None = None
    story_purpose: str | None = None
    visual_description: str | None = None
    asset_url: str | None = None
    fallback_panel_index: int | None = Field(default=None, ge=1, le=4)
    image_prompt: str
    audio_start_ms: int = Field(ge=0)
    audio_end_ms: int = Field(ge=0)


class StorybookExperienceSessionData(BaseModel):
    storybook_id: UUID
    version: int = Field(ge=1)
    source_recording_id: UUID
    duration_ms: int = Field(gt=0)
    url: str
    expires_at: int
    storyline_schema_version: str
    scenes: list[StorybookExperienceSceneData]
    cues: list[StorybookExperienceCueData]
    narrator_provider: str | None = None
    narrator_voice: str | None = None
    music_source: str | None = None


class StoryPlanClipData(BaseModel):
    source_segment_id: UUID
    speaker_key: str
    speaker_name: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str
    included: bool
    locked: bool
    role: Literal["original"]


class StoryPlanSceneData(BaseModel):
    scene_index: int = Field(ge=0)
    page_index: int = Field(ge=0)
    type: Literal["cover", "story", "ending"]
    scene_kind: str
    story_purpose: str
    title: str
    narration: str
    quote: str | None = None
    source_segment_id: UUID | None = None
    speaker_name: str | None = None
    visual_description: str
    image_prompt: str
    asset_url: str | None = None
    fallback_panel_index: int = Field(ge=1, le=4)
    audio_sequence: list[dict]
    traceability: dict


class StoryPlanData(BaseModel):
    id: UUID
    storybook_id: UUID
    storybook_version_id: UUID
    source_recording_id: UUID
    status: Literal["DRAFT", "CONFIRMED"]
    revision: int = Field(ge=1)
    source_schema_version: str
    director_schema_version: str
    source_story: dict
    director_script: dict
    created_at: datetime
    updated_at: datetime


class StoryPlanClipSelection(BaseModel):
    source_segment_id: UUID
    included: bool


class UpdateStoryPlanRequest(BaseModel):
    clips: list[StoryPlanClipSelection]
    narration_style: str = Field(default="温暖克制", min_length=2, max_length=32)
    status: Literal["DRAFT", "CONFIRMED"] = "DRAFT"

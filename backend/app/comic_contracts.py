from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ComicPanelData(BaseModel):
    id: UUID
    panel_index: int = Field(ge=1, le=4)
    narration: str
    dialogue: str | None = None
    source_segment_id: UUID | None = None
    asset_url: str
    asset_variant: str
    crop_x: int = Field(ge=0, le=1)
    crop_y: int = Field(ge=0, le=1)
    prompt: str
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ComicData(BaseModel):
    id: UUID
    moment_id: UUID
    title: str
    status: str
    version: int
    pipeline_version: str
    metadata: dict
    panels: list[ComicPanelData]
    created_at: datetime
    updated_at: datetime

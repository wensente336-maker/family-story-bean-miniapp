from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PodcastReleaseMetricsData(BaseModel):
    rollout_mode: str
    creation_enabled: bool
    sharing_enabled: bool
    generation_total: int
    generation_completed: int
    generation_failed: int
    first_pass_success_rate: float | None
    usable_product_rate: float | None
    degradation_rate: float | None
    generation_p95_seconds: float | None
    failure_reasons: dict[str, int]
    active_shares: int
    share_accesses: int


class PodcastRollbackRequest(BaseModel):
    confirmation: Literal["ROLLBACK_TO_PREVIOUS_COMPLETED"]


class PodcastRollbackData(BaseModel):
    recording_id: UUID
    from_version: int
    to_version: int
    podcast_version_id: UUID
    revoked_share_count: int


class RevokeAllTestSharesRequest(BaseModel):
    confirmation: Literal["REVOKE_ALL_TEST_SHARES"]


class RevokeAllTestSharesData(BaseModel):
    revoked_share_count: int

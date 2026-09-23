from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_release import PostgresPodcastReleaseRepository, PodcastReleaseRepository
from .podcast_release_contracts import (
    PodcastReleaseMetricsData, PodcastRollbackData, PodcastRollbackRequest,
    RevokeAllTestSharesData, RevokeAllTestSharesRequest,
)


router = APIRouter(prefix="/v1/ops", tags=["podcast-release"])


def get_podcast_release_repository() -> PodcastReleaseRepository:
    return PostgresPodcastReleaseRepository(get_settings().database_url)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


@router.get("/podcast-metrics", response_model=ApiResponse[PodcastReleaseMetricsData])
def podcast_metrics(
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastReleaseRepository = Depends(get_podcast_release_repository),
):
    values = repository.metrics(user_id)
    if values is None:
        raise HTTPException(status_code=404, detail={
            "code": "FAMILY_NOT_FOUND", "message": "家庭不存在",
            "retryable": False, "details": {},
        })
    settings = get_settings()
    return ApiResponse(data=PodcastReleaseMetricsData(
        rollout_mode=settings.podcast_rollout_mode,
        creation_enabled=settings.podcast_creation_enabled,
        sharing_enabled=settings.podcast_sharing_enabled,
        **values,
    ), meta=meta_for(request))


@router.post(
    "/recordings/{recording_id}/rollback",
    response_model=ApiResponse[PodcastRollbackData],
)
def rollback_podcast(
    recording_id: UUID, _body: PodcastRollbackRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastReleaseRepository = Depends(get_podcast_release_repository),
):
    result = repository.rollback(user_id, recording_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "PODCAST_ROLLBACK_UNAVAILABLE",
            "message": "没有可回退的上一稳定播客版本",
            "retryable": False, "details": {},
        })
    return ApiResponse(data=PodcastRollbackData.model_validate(result), meta=meta_for(request))


@router.post(
    "/podcast-shares/revoke-all-test",
    response_model=ApiResponse[RevokeAllTestSharesData],
)
def revoke_all_test_shares(
    _body: RevokeAllTestSharesRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastReleaseRepository = Depends(get_podcast_release_repository),
):
    count = repository.revoke_all_shares(user_id)
    return ApiResponse(
        data=RevokeAllTestSharesData(revoked_share_count=count), meta=meta_for(request)
    )

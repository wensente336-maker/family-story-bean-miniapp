from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_audio import LocalPodcastRenderer
from .podcast_contracts import (
    CreatePodcastRequest, PodcastData, PodcastPlaybackData, RemixPodcastRequest,
)
from .podcast_repository import PodcastRepository, PostgresPodcastRepository
from .recording_router import get_object_storage
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["podcasts"])


def get_podcast_repository() -> PodcastRepository:
    settings = get_settings()
    return PostgresPodcastRepository(settings.database_url, LocalPodcastRenderer(settings))


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message="播客不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "PODCAST_NOT_FOUND", "message": message, "retryable": False, "details": {}},
    )


@router.post("/podcasts", response_model=ApiResponse[PodcastData])
def create_podcast(
    body: CreatePodcastRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRepository = Depends(get_podcast_repository),
):
    podcast = repository.create(user_id, body.moment_ids, get_settings().pipeline_version)
    if podcast is None:
        not_found("请选择 1–3 个同一录音中已保留的高光")
    return ApiResponse(data=PodcastData.model_validate(podcast), meta=meta_for(request))


@router.get("/podcasts/{podcast_id}", response_model=ApiResponse[PodcastData])
def get_podcast(
    podcast_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastRepository = Depends(get_podcast_repository),
):
    podcast = repository.get_for_user(user_id, podcast_id)
    if podcast is None:
        not_found()
    return ApiResponse(data=PodcastData.model_validate(podcast), meta=meta_for(request))


@router.patch("/podcasts/{podcast_id}", response_model=ApiResponse[PodcastData])
def remix_podcast(
    podcast_id: UUID, body: RemixPodcastRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRepository = Depends(get_podcast_repository),
):
    podcast = repository.remix(user_id, podcast_id, body.moment_ids, body.intro, body.outro)
    if podcast is None:
        not_found("播客或所选高光不存在")
    return ApiResponse(data=PodcastData.model_validate(podcast), meta=meta_for(request))


@router.post(
    "/podcasts/{podcast_id}/playback-url", response_model=ApiResponse[PodcastPlaybackData]
)
def podcast_playback_url(
    podcast_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastRepository = Depends(get_podcast_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    podcast = repository.get_for_user(user_id, podcast_id)
    if podcast is None or podcast["status"] != "COMPLETED" or not podcast.get("object_key"):
        not_found("播客音频尚未可用")
    token, expires_at = storage.issue_playback_token(
        podcast["recording_id"], podcast["object_key"], "audio/mpeg"
    )
    base = str(request.base_url).rstrip("/") + f"/v1/playback/{token}"
    return ApiResponse(
        data=PodcastPlaybackData(url=base, download_url=f"{base}?download=true", expires_at=expires_at),
        meta=meta_for(request),
    )

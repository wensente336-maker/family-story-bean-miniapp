from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_audio import LocalPodcastRenderer
from .podcast_contracts import (
    PodcastRenderPlaybackData,
    PodcastRenderResultData,
)
from .podcast_render_repository import (
    PodcastRenderRepository,
    PostgresPodcastRenderRepository,
)
from .podcast_render_service import PodcastRenderService
from .podcast_release import PodcastReleasePolicy
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["podcast-render"])


def dispatch_render(
    job_id: UUID, background_tasks: BackgroundTasks, service: PodcastRenderService
) -> None:
    if get_settings().podcast_render_dispatcher.strip().lower() == "celery":
        from worker.main import render_podcast

        render_podcast.apply_async(
            args=[str(job_id)], queue="podcast", task_id=f"podcast-render-{job_id}"
        )
        return
    background_tasks.add_task(service.run, job_id)


def get_podcast_render_repository() -> PodcastRenderRepository:
    return PostgresPodcastRenderRepository(get_settings().database_url)


def get_podcast_render_service(
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
) -> PodcastRenderService:
    return PodcastRenderService(repository, LocalPodcastRenderer(get_settings()))


def get_render_storage() -> LocalObjectStorage:
    return LocalObjectStorage(get_settings())


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def render_not_found(message: str = "播客生成任务不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "PODCAST_RENDER_NOT_FOUND",
            "message": message,
            "retryable": False,
            "details": {},
        },
    )


@router.post(
    "/recordings/{recording_id}/podcast-render-jobs",
    response_model=ApiResponse[PodcastRenderResultData],
)
def create_podcast_render_job(
    recording_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
    service: PodcastRenderService = Depends(get_podcast_render_service),
):
    if not PodcastReleasePolicy(get_settings()).can_create(user_id):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "PODCAST_CREATION_PAUSED", "message": "家庭播客生成已暂停，已有作品仍可播放和下载",
            "retryable": True, "details": {},
        })
    result = repository.create_job(user_id, recording_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PODCAST_PLAN_NOT_CONFIRMED",
                "message": "请先确认并锁定播客策划",
                "retryable": False,
                "details": {},
            },
        )
    if result["job"]["status"] == "CREATED":
        dispatch_render(result["job"]["id"], background_tasks, service)
    return ApiResponse(
        data=PodcastRenderResultData.model_validate(result), meta=meta_for(request)
    )


@router.get(
    "/podcast-render-jobs/{job_id}",
    response_model=ApiResponse[PodcastRenderResultData],
)
def get_podcast_render_job(
    job_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
):
    result = repository.get_for_user(user_id, job_id)
    if result is None:
        render_not_found()
    return ApiResponse(
        data=PodcastRenderResultData.model_validate(result), meta=meta_for(request)
    )


@router.get(
    "/recordings/{recording_id}/podcast-render-job",
    response_model=ApiResponse[PodcastRenderResultData],
)
def get_recording_podcast_render_job(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
):
    result = repository.get_by_recording(user_id, recording_id)
    if result is None:
        render_not_found()
    return ApiResponse(
        data=PodcastRenderResultData.model_validate(result), meta=meta_for(request)
    )


@router.post(
    "/podcast-render-jobs/{job_id}/retry",
    response_model=ApiResponse[PodcastRenderResultData],
)
def retry_podcast_render_job(
    job_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
    service: PodcastRenderService = Depends(get_podcast_render_service),
):
    result = repository.reset_for_retry(user_id, job_id)
    if result is None:
        render_not_found("只有失败的播客任务可以重试")
    dispatch_render(job_id, background_tasks, service)
    return ApiResponse(
        data=PodcastRenderResultData.model_validate(result), meta=meta_for(request)
    )


@router.post(
    "/podcast-render-jobs/{job_id}/playback-url",
    response_model=ApiResponse[PodcastRenderPlaybackData],
)
def create_render_playback_url(
    job_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastRenderRepository = Depends(get_podcast_render_repository),
    storage: LocalObjectStorage = Depends(get_render_storage),
):
    result = repository.get_for_user(user_id, job_id)
    if result is None:
        render_not_found()
    if result["job"]["status"] != "COMPLETED" or not result["object_key"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PODCAST_RENDER_NOT_READY",
                "message": "播客音频尚未生成完成",
                "retryable": True,
                "details": {},
            },
        )
    # The object key already contains the authoritative recording id. Resolve it
    # without exposing a broad storage path or accepting a client-provided id.
    try:
        recording_id = UUID(
            result["object_key"].split("/recordings/", 1)[1].split("/", 1)[0]
        )
    except (IndexError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "PODCAST_ASSET_INVALID",
                "message": "播客音频资产路径无效",
                "retryable": False,
                "details": {},
            },
        ) from exc
    token, expires_at = storage.issue_playback_token(
        recording_id, result["object_key"], "audio/mpeg"
    )
    base = str(request.base_url).rstrip("/")
    url = f"{base}/v1/playback/{token}"
    return ApiResponse(
        data=PodcastRenderPlaybackData(
            url=url,
            download_url=f"{url}?download=true",
            expires_at=expires_at,
            render_metadata=result["render_metadata"],
        ),
        meta=meta_for(request),
    )

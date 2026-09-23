from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_contracts import (
    PodcastMaterialWorkspaceData,
    UpdatePodcastMaterialSetRequest,
)
from .podcast_material_repository import (
    PodcastMaterialRepository,
    PostgresPodcastMaterialRepository,
)
from .podcast_release import PodcastReleasePolicy
from .highlight_repository import HighlightRepository, PostgresHighlightRepository
from .highlight_router import get_highlight_storage, prepare_audio
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["podcast-materials"])


def get_podcast_material_repository() -> PodcastMaterialRepository:
    return PostgresPodcastMaterialRepository(get_settings().database_url)


def get_material_highlight_repository() -> HighlightRepository:
    return PostgresHighlightRepository(get_settings().database_url)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message: str = "声音素材不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "PODCAST_MATERIALS_NOT_FOUND",
            "message": message,
            "retryable": False,
            "details": {},
        },
    )


@router.get(
    "/recordings/{recording_id}/podcast-material-set",
    response_model=ApiResponse[PodcastMaterialWorkspaceData],
)
def get_material_set(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastMaterialRepository = Depends(get_podcast_material_repository),
):
    material_set = repository.get_for_user(user_id, recording_id)
    if material_set is None:
        not_found()
    return ApiResponse(
        data=PodcastMaterialWorkspaceData.model_validate(material_set),
        meta=meta_for(request),
    )


@router.post(
    "/recordings/{recording_id}/podcast-material-set/draft",
    response_model=ApiResponse[PodcastMaterialWorkspaceData],
)
def create_material_set_draft(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastMaterialRepository = Depends(get_podcast_material_repository),
):
    if not PodcastReleasePolicy(get_settings()).can_create(user_id):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "PODCAST_CREATION_PAUSED", "message": "家庭播客创建暂未对当前用户开放",
            "retryable": True, "details": {},
        })
    material_set = repository.get_or_create_draft(user_id, recording_id)
    if material_set is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PODCAST_SOURCE_REQUIRED",
                "message": "请先保留 1–10 个带原声证据的家庭高光",
                "retryable": False,
                "details": {},
            },
        )
    return ApiResponse(
        data=PodcastMaterialWorkspaceData.model_validate(material_set),
        meta=meta_for(request),
    )


@router.put(
    "/recordings/{recording_id}/podcast-material-set",
    response_model=ApiResponse[PodcastMaterialWorkspaceData],
)
def update_material_set(
    recording_id: UUID,
    body: UpdatePodcastMaterialSetRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastMaterialRepository = Depends(get_podcast_material_repository),
    highlight_repository: HighlightRepository = Depends(get_material_highlight_repository),
    highlight_storage: LocalObjectStorage = Depends(get_highlight_storage),
):
    try:
        material_set = repository.update(
            user_id,
            recording_id,
            body.status,
            [item.model_dump() for item in body.materials],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_PODCAST_MATERIAL_RANGE",
                "message": str(exc),
                "retryable": False,
                "details": {},
            },
        ) from exc
    if material_set is None:
        not_found("声音素材草稿不存在、已确认或包含无效家庭成员")
    # Only the real persistent material repository owns this cross-aggregate
    # projection. In-memory/adaptor repositories can implement their own hook.
    if body.status == "CONFIRMED" and isinstance(repository, PostgresPodcastMaterialRepository):
        for item in material_set.get("materials", []):
            moment_id = item.get("source_moment_id")
            if moment_id:
                work = highlight_repository.save_from_moment(
                    user_id, moment_id, item.get("share_allowed", True)
                )
                if work:
                    prepare_audio(work, highlight_repository, highlight_storage)
    return ApiResponse(
        data=PodcastMaterialWorkspaceData.model_validate(material_set),
        meta=meta_for(request),
    )

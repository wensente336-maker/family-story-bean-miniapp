from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .comic_contracts import ComicData
from .comic_repository import ComicRepository, PostgresComicRepository
from .config import get_settings
from .contracts import ApiMeta, ApiResponse


router = APIRouter(prefix="/v1", tags=["comics"])


def get_comic_repository() -> ComicRepository:
    return PostgresComicRepository(get_settings().database_url)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message="漫画不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "COMIC_NOT_FOUND", "message": message, "retryable": False, "details": {}},
    )


def require_comic_creation_enabled():
    if not get_settings().comic_creation_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COMIC_CREATION_DISABLED",
                "message": "家庭漫画创作已归档，请使用家庭播客",
                "retryable": False,
                "details": {},
            },
        )


@router.post("/moments/{moment_id}/comics", response_model=ApiResponse[ComicData])
def create_comic(
    moment_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: ComicRepository = Depends(get_comic_repository),
    _enabled: None = Depends(require_comic_creation_enabled),
):
    comic = repository.create_for_moment(user_id, moment_id, get_settings().pipeline_version)
    if comic is None:
        not_found("请先保留该高光，再生成漫画")
    return ApiResponse(data=ComicData.model_validate(comic), meta=meta_for(request))


@router.get("/comics/{comic_id}", response_model=ApiResponse[ComicData])
def get_comic(
    comic_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: ComicRepository = Depends(get_comic_repository),
):
    comic = repository.get_for_user(user_id, comic_id)
    if comic is None:
        not_found()
    return ApiResponse(data=ComicData.model_validate(comic), meta=meta_for(request))


@router.post("/comics/{comic_id}/panels/{panel_index}/regenerate", response_model=ApiResponse[ComicData])
def regenerate_panel(
    comic_id: UUID, panel_index: int, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: ComicRepository = Depends(get_comic_repository),
    _enabled: None = Depends(require_comic_creation_enabled),
):
    if panel_index not in range(1, 5):
        not_found("分镜不存在")
    comic = repository.regenerate_panel(user_id, comic_id, panel_index)
    if comic is None:
        not_found("分镜不存在或无权访问")
    return ApiResponse(data=ComicData.model_validate(comic), meta=meta_for(request))

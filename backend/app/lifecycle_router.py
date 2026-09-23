from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .lifecycle_contracts import (
    CreateShareRequest, DeleteResultData, FamilyMetricsData, PrivacySettingsData,
    PublicShareData, ShareData, TimelineData, TimelineItemData,
    UpdatePrivacySettingsRequest,
)
from .lifecycle_repository import LifecycleRepository, PostgresLifecycleRepository
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["timeline-privacy"])


def get_lifecycle_repository() -> LifecycleRepository:
    settings = get_settings()
    return PostgresLifecycleRepository(
        settings.database_url, LocalObjectStorage(settings)
    )


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message: str):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "retryable": False, "details": {}},
    )


def share_payload(row: dict, url: str) -> ShareData:
    return ShareData(
        id=row["id"], creation_id=row["creation_id"],
        creation_type=row["creation_type"], title=row.get("title") or "家庭作品",
        url=url, expires_at=row["expires_at"], revoked_at=row.get("revoked_at"),
        access_count=row.get("access_count", 0), created_at=row["created_at"],
    )


@router.get("/timeline", response_model=ApiResponse[TimelineData])
def timeline(
    request: Request,
    content_type: str | None = Query(default=None, pattern="^(recording|moment|comic|podcast)$"),
    member_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    items = repository.timeline(user_id, content_type, member_id, date_from, date_to, limit)
    return ApiResponse(
        data=TimelineData(items=[TimelineItemData.model_validate(item) for item in items], total=len(items)),
        meta=meta_for(request),
    )


@router.post("/creations/{creation_id}/shares", response_model=ApiResponse[ShareData])
def create_share(
    creation_id: UUID, body: CreateShareRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    share = repository.create_share(user_id, creation_id, body.expires_in_hours)
    if share is None:
        not_found("作品不存在、尚未完成或家庭已关闭分享")
    url = f"{get_settings().public_web_base_url.rstrip('/')}/share/{share['token']}"
    return ApiResponse(data=share_payload(share, url), meta=meta_for(request))


@router.get("/shares", response_model=ApiResponse[list[ShareData]])
def list_shares(
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    shares = [share_payload(item, "") for item in repository.list_shares(user_id)]
    return ApiResponse(data=shares, meta=meta_for(request))


@router.delete("/shares/{share_id}", response_model=ApiResponse[ShareData])
def revoke_share(
    share_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    revoked = repository.revoke_share(user_id, share_id)
    if revoked is None:
        not_found("分享链接不存在或无权访问")
    return ApiResponse(data=share_payload(revoked, ""), meta=meta_for(request))


@router.get("/public/shares/{token}", response_model=ApiResponse[PublicShareData])
def public_share(
    token: str, request: Request,
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    share = repository.resolve_share(token)
    if share is None:
        not_found("分享链接已过期或已撤销")
    media_url = None
    if share["creation_type"] == "PODCAST" and share.get("object_key"):
        media_url = str(request.base_url).rstrip("/") + f"/v1/public/shares/{token}/media"
    return ApiResponse(
        data=PublicShareData(
            creation_id=share["creation_id"], creation_type=share["creation_type"],
            title=share.get("title") or "家庭作品", expires_at=share["expires_at"],
            media_url=media_url, panels=share.get("panels", []),
        ),
        meta=meta_for(request),
    )


@router.get("/public/shares/{token}/media")
def public_share_media(
    token: str, repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    share = repository.resolve_share(token, count_access=False)
    if share is None or share["creation_type"] != "PODCAST" or not share.get("object_key"):
        not_found("分享音频已过期或不存在")
    path = repository.storage.path_for(share["object_key"])
    if not path.exists():
        not_found("分享音频已被删除")
    return FileResponse(path, media_type="audio/mpeg", filename=f"{share['title']}.mp3")


@router.get("/privacy", response_model=ApiResponse[PrivacySettingsData])
def privacy_settings(
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    settings = repository.get_privacy_settings(user_id)
    if settings is None:
        not_found("请先创建家庭")
    return ApiResponse(data=PrivacySettingsData.model_validate(settings), meta=meta_for(request))


@router.put("/privacy", response_model=ApiResponse[PrivacySettingsData])
def update_privacy_settings(
    body: UpdatePrivacySettingsRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    settings = repository.update_privacy_settings(
        user_id, body.recording_retention_days, body.share_default_hours, body.sharing_enabled
    )
    if settings is None:
        not_found("请先创建家庭")
    return ApiResponse(data=PrivacySettingsData.model_validate(settings), meta=meta_for(request))


@router.delete("/privacy/creations/{creation_id}", response_model=ApiResponse[DeleteResultData])
def delete_creation(
    creation_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    result = repository.delete_creation(user_id, creation_id)
    if result is None:
        not_found("作品不存在或无权删除")
    return ApiResponse(data=DeleteResultData.model_validate(result), meta=meta_for(request))


@router.delete("/privacy/recordings/{recording_id}", response_model=ApiResponse[DeleteResultData])
def delete_recording(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    result = repository.delete_recording(user_id, recording_id)
    if result is None:
        not_found("录音不存在或无权删除")
    return ApiResponse(data=DeleteResultData.model_validate(result), meta=meta_for(request))


@router.delete("/privacy/families/{family_id}", response_model=ApiResponse[DeleteResultData])
def delete_family(
    family_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    result = repository.delete_family(user_id, family_id)
    if result is None:
        not_found("家庭不存在或无权删除")
    return ApiResponse(data=DeleteResultData.model_validate(result), meta=meta_for(request))


@router.get("/ops/family-metrics", response_model=ApiResponse[FamilyMetricsData])
def family_metrics(
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: LifecycleRepository = Depends(get_lifecycle_repository),
):
    metrics = repository.metrics(user_id)
    if metrics is None:
        not_found("请先创建家庭")
    return ApiResponse(data=FamilyMetricsData.model_validate(metrics), meta=meta_for(request))

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_share_contracts import (
    CreatePodcastShareRequest, PodcastShareData, PublicPodcastShareData,
)
from .podcast_share_repository import (
    PodcastShareNotAllowed, PodcastShareRepository, PostgresPodcastShareRepository,
)
from .podcast_release import PodcastReleasePolicy
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["podcast-sharing"])


def get_podcast_share_repository() -> PodcastShareRepository:
    return PostgresPodcastShareRepository(get_settings().database_url)


def get_share_storage() -> LocalObjectStorage:
    return LocalObjectStorage(get_settings())


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def share_not_found(message="分享链接不存在、已过期或已撤销"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "PODCAST_SHARE_NOT_FOUND", "message": message, "retryable": False, "details": {}},
    )


def owner_payload(row: dict, url: str = "") -> PodcastShareData:
    return PodcastShareData(
        id=row["id"], podcast_version_id=row["podcast_version_id"],
        recording_id=row["recording_id"], title=row["title"], url=url,
        expires_at=row["expires_at"], revoked_at=row.get("revoked_at"),
        access_count=row.get("access_count", 0), created_at=row["created_at"],
    )


def public_payload(row: dict, request: Request, storage: LocalObjectStorage, share_token: str) -> PublicPodcastShareData:
    recording_id = row["recording_id"]
    audio_token, _ = storage.issue_playback_token(recording_id, row["object_key"], "audio/mpeg", share_token=share_token)
    base = str(request.base_url).rstrip("/")
    cover_url = cover_download_url = None
    if row.get("cover_object_key"):
        cover_token, _ = storage.issue_playback_token(
            recording_id, row["cover_object_key"], "image/webp", share_token=share_token
        )
        cover_url = f"{base}/v1/playback/{cover_token}"
        cover_download_url = f"{cover_url}?download=true"
    metadata = row.get("render_metadata") or {}
    return PublicPodcastShareData(
        title=row["title"], description=row["description"], tags=row.get("tags") or [],
        cover_url=cover_url, cover_download_url=cover_download_url,
        media_url=f"{base}/v1/playback/{audio_token}", expires_at=row["expires_at"],
        duration_ms=max(0, int(metadata.get("duration_ms") or 0)),
        render_mode=metadata.get("render_mode") if metadata.get("render_mode") in {"narrated", "original_only"} else "original_only",
    )


@router.post(
    "/recordings/{recording_id}/podcast-shares",
    response_model=ApiResponse[PodcastShareData],
)
def create_podcast_share(
    recording_id: UUID, body: CreatePodcastShareRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastShareRepository = Depends(get_podcast_share_repository),
):
    if not PodcastReleasePolicy(get_settings()).can_share(user_id):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "PODCAST_SHARING_PAUSED", "message": "新分享创建已暂停，站内播放与下载不受影响",
            "retryable": True, "details": {},
        })
    try:
        share = repository.create(user_id, recording_id, body.expires_in_hours)
    except PodcastShareNotAllowed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "PODCAST_SHARE_NOT_ALLOWED",
            "message": "作品包含仅限家庭内部使用的原声，不能创建外部分享链接",
            "retryable": False,
            "details": {},
        })
    if share is None:
        share_not_found("播客不存在、尚未完成或家庭已关闭分享")
    base = str(request.base_url).rstrip("/")
    url = f"{base}/v1/public/podcast-shares/{share['token']}/card"
    return ApiResponse(data=owner_payload(share, url), meta=meta_for(request))


@router.get("/podcast-shares", response_model=ApiResponse[list[PodcastShareData]])
def list_podcast_shares(
    request: Request, recording_id: UUID | None = None,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastShareRepository = Depends(get_podcast_share_repository),
):
    return ApiResponse(
        data=[owner_payload(item) for item in repository.list_for_user(user_id, recording_id)],
        meta=meta_for(request),
    )


@router.delete("/podcast-shares/{share_id}", response_model=ApiResponse[PodcastShareData])
def revoke_podcast_share(
    share_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastShareRepository = Depends(get_podcast_share_repository),
):
    share = repository.revoke(user_id, share_id)
    if share is None:
        share_not_found("分享链接不存在或无权撤销")
    return ApiResponse(data=owner_payload(share), meta=meta_for(request))


@router.get(
    "/public/podcast-shares/{token}",
    response_model=ApiResponse[PublicPodcastShareData],
)
def resolve_podcast_share(
    token: str, request: Request,
    repository: PodcastShareRepository = Depends(get_podcast_share_repository),
    storage: LocalObjectStorage = Depends(get_share_storage),
):
    share = repository.resolve(token)
    if share is None:
        share_not_found()
    return ApiResponse(data=public_payload(share, request, storage, token), meta=meta_for(request))


@router.get("/public/podcast-shares/{token}/card", response_class=HTMLResponse)
def podcast_share_card(
    token: str, request: Request,
    repository: PodcastShareRepository = Depends(get_podcast_share_repository),
    storage: LocalObjectStorage = Depends(get_share_storage),
):
    share = repository.resolve(token, count_access=True)
    if share is None:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>链接已失效</title><main><h1>这份家庭记忆已无法访问</h1><p>链接可能已过期或被家人撤销。</p></main>",
            status_code=404,
        )
    public = public_payload(share, request, storage, token)
    title, description = escape(public.title), escape(public.description or "一段来自家里的声音")
    cover_meta = f'<meta property="og:image" content="{escape(public.cover_url)}">' if public.cover_url else ""
    cover = f'<img src="{escape(public.cover_url)}" alt="播客封面">' if public.cover_url else '<div class="wave">〜 家庭声波 〜</div>'
    tags = " ".join(f"<span>#{escape(item)}</span>" for item in public.tags)
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · 家庭故事豆</title>
<meta name="description" content="{description}"><meta property="og:type" content="music.song">
<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">
{cover_meta}<meta property="og:audio" content="{escape(public.media_url)}">
<style>body{{margin:0;padding:40px 18px;background:#f3eee6;color:#173b3d;font-family:system-ui}}main{{max-width:680px;margin:auto}}img,.wave{{width:min(100%,520px);aspect-ratio:1;object-fit:cover;border-radius:28px;background:#173b3d;color:#f4c96f;display:grid;place-items:center}}h1{{font-size:clamp(32px,7vw,54px)}}p{{color:#6e7772;line-height:1.7}}audio{{width:100%;margin:22px 0}}span{{margin-right:8px;color:#a45f4d}}small{{display:block;margin-top:24px;color:#858b86}}</style></head>
<body><main>{cover}<h1>{title}</h1><p>{description}</p><div>{tags}</div><audio controls src="{escape(public.media_url)}"></audio><small>家庭故事豆 · 限时私密分享 · 有效至 {escape(public.expires_at.isoformat())}</small></main></body></html>"""
    return HTMLResponse(html)

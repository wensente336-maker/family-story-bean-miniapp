from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .storybook_contracts import (
    StorybookAudioClipData,
    StorybookAudioSessionData,
    StorybookExperienceSessionData,
    StoryPlanData,
    StorybookData,
    UpdateStoryPlanRequest,
    StorybookVersionData,
    StorybookVersionSummary,
)
from .storybook_director import (
    DIRECTOR_SCHEMA_VERSION,
    SOURCE_SCHEMA_VERSION,
    SoundStoryDirector,
    selection_map,
)
from .storybook_audio import StorybookAudioRenderer, StorybookAudioRenderError
from .storybook_experience import StorybookExperienceError, StorybookExperienceRenderer
from .storybook_repository import PostgresStorybookRepository, StorybookRepository
from .recording_router import get_object_storage
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["storybooks"])


def get_storybook_repository() -> StorybookRepository:
    return PostgresStorybookRepository(get_settings().database_url)


def get_storybook_audio_renderer(
    storage: LocalObjectStorage = Depends(get_object_storage),
) -> StorybookAudioRenderer:
    return StorybookAudioRenderer(storage)


def get_storybook_experience_renderer() -> StorybookExperienceRenderer:
    return StorybookExperienceRenderer(get_settings())


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message="电子书不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "STORYBOOK_NOT_FOUND",
            "message": message,
            "retryable": False,
            "details": {},
        },
    )


def _save_director_plan(repository: StorybookRepository, context: dict, composed: dict, status_value: str):
    return repository.save_story_plan({
        "family_id": context["family_id"],
        "storybook_version_id": context["storybook_version_id"],
        "source_recording_id": context["source_recording_id"],
        "status": status_value,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "director_schema_version": DIRECTOR_SCHEMA_VERSION,
        "source_story": composed["source_story"],
        "director_script": composed["director_script"],
    })


@router.post(
    "/comics/{comic_id}/storybook",
    response_model=ApiResponse[StorybookData],
    summary="创建电子书或同步漫画的新版本",
)
def create_or_refresh_storybook(
    comic_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
):
    storybook = repository.create_or_refresh(user_id, comic_id)
    if storybook is None:
        not_found("漫画不存在或无权生成电子书")
    return ApiResponse(data=StorybookData.model_validate(storybook), meta=meta_for(request))


@router.get(
    "/storybooks/{storybook_id}",
    response_model=ApiResponse[StorybookData],
    summary="读取电子书当前版本",
)
def get_storybook(
    storybook_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
):
    storybook = repository.get_for_user(user_id, storybook_id)
    if storybook is None:
        not_found()
    return ApiResponse(data=StorybookData.model_validate(storybook), meta=meta_for(request))


@router.get(
    "/storybooks/{storybook_id}/versions",
    response_model=ApiResponse[list[StorybookVersionSummary]],
    summary="列出电子书的不可变版本",
)
def list_storybook_versions(
    storybook_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
):
    versions = repository.list_versions(user_id, storybook_id)
    if versions is None:
        not_found()
    return ApiResponse(
        data=[StorybookVersionSummary.model_validate(item) for item in versions],
        meta=meta_for(request),
    )


@router.get(
    "/storybooks/{storybook_id}/versions/{version}",
    response_model=ApiResponse[StorybookVersionData],
    summary="读取指定电子书版本",
)
def get_storybook_version(
    storybook_id: UUID,
    version: int,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
):
    if version < 1:
        not_found("电子书版本不存在")
    item = repository.get_version(user_id, storybook_id, version)
    if item is None:
        not_found("电子书版本不存在或无权访问")
    return ApiResponse(data=StorybookVersionData.model_validate(item), meta=meta_for(request))


@router.post(
    "/storybooks/{storybook_id}/story-plan/draft",
    response_model=ApiResponse[StoryPlanData],
    summary="从用户标注原声生成声音优先的导演草案",
)
def create_story_plan_draft(
    storybook_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
):
    context = repository.get_story_source_context(user_id, storybook_id)
    if context is None:
        not_found()
    existing = repository.get_story_plan(context["storybook_version_id"])
    if existing is not None:
        return ApiResponse(data=StoryPlanData.model_validate(existing), meta=meta_for(request))
    composed = SoundStoryDirector().compose(context)
    plan = _save_director_plan(repository, context, composed, "DRAFT")
    return ApiResponse(data=StoryPlanData.model_validate(plan), meta=meta_for(request))


@router.patch(
    "/storybooks/{storybook_id}/story-plan",
    response_model=ApiResponse[StoryPlanData],
    summary="更新原声取舍并重新生成导演脚本",
)
def update_story_plan(
    storybook_id: UUID,
    payload: UpdateStoryPlanRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    context = repository.get_story_source_context(user_id, storybook_id)
    if context is None:
        not_found()
    existing = repository.get_story_plan(context["storybook_version_id"])
    if existing is None:
        current_selections: dict[str, bool] = {}
    else:
        current_selections = selection_map(existing["source_story"].get("clips", []))
    allowed_ids = {str(item["id"]) for item in context["transcript_segments"]}
    for item in payload.clips:
        if str(item.source_segment_id) not in allowed_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INVALID_STORY_SOURCE",
                    "message": "声音故事线包含不属于当前高光的原声片段",
                    "retryable": False,
                    "details": {"source_segment_id": str(item.source_segment_id)},
                },
            )
        current_selections[str(item.source_segment_id)] = item.included
    if current_selections and not any(current_selections.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "STORY_SOURCE_REQUIRED",
                "message": "至少保留一段家庭原声，才能形成声音故事线",
                "retryable": False,
                "details": {},
            },
        )
    composed = SoundStoryDirector().compose(
        context, current_selections, payload.narration_style
    )
    plan = _save_director_plan(repository, context, composed, payload.status)
    old_object_key = repository.invalidate_experience_track(context["storybook_version_id"])
    if old_object_key:
        storage.delete(old_object_key)
    return ApiResponse(data=StoryPlanData.model_validate(plan), meta=meta_for(request))


@router.post(
    "/storybooks/{storybook_id}/audio-session",
    response_model=ApiResponse[StorybookAudioSessionData],
    summary="生成书页原声并签发短时播放地址",
)
def create_storybook_audio_session(
    storybook_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
    renderer: StorybookAudioRenderer = Depends(get_storybook_audio_renderer),
):
    context = repository.get_audio_context(user_id, storybook_id)
    if context is None:
        not_found()
    existing = {
        asset["page_index"]: asset
        for asset in repository.list_audio_assets(context["storybook_version_id"])
    }
    clips = []
    expiries = []
    for page in context["manifest"]["pages"]:
        source = page.get("clip")
        if source is None:
            continue
        page_index = page["index"]
        asset = existing.get(page_index)
        if asset is None or not storage.path_for(asset["object_key"]).exists():
            if not context.get("source_object_key"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "STORYBOOK_AUDIO_SOURCE_UNAVAILABLE",
                        "message": "原始录音已清理，且书页原声尚未生成",
                        "retryable": False,
                        "details": {"page_index": page_index},
                    },
                )
            object_key = (
                f"families/{context['family_id']}/recordings/{context['source_recording_id']}"
                f"/storybooks/{storybook_id}/v{context['current_version']}"
                f"/page-{page_index:02d}-original.mp3"
            )
            try:
                duration_ms = renderer.render_clip(
                    context["source_object_key"], object_key,
                    source["start_ms"], source["end_ms"],
                )
            except StorybookAudioRenderError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "code": "STORYBOOK_AUDIO_RENDER_FAILED",
                        "message": str(exc),
                        "retryable": True,
                        "details": {"page_index": page_index},
                    },
                ) from exc
            asset = repository.save_audio_asset({
                "family_id": context["family_id"],
                "storybook_version_id": context["storybook_version_id"],
                "page_index": page_index,
                "source_recording_id": context["source_recording_id"],
                "source_segment_id": (
                    source["source_segment_id"]
                    if isinstance(source["source_segment_id"], UUID)
                    else UUID(source["source_segment_id"])
                ),
                "original_start_ms": source["start_ms"],
                "original_end_ms": source["end_ms"],
                "object_key": object_key,
                "duration_ms": duration_ms,
            })
        token, expires_at = storage.issue_playback_token(
            context["source_recording_id"], asset["object_key"], asset["media_type"]
        )
        expiries.append(expires_at)
        clips.append(StorybookAudioClipData(
            page_index=page_index,
            source_segment_id=asset["source_segment_id"],
            original_start_ms=asset["original_start_ms"],
            original_end_ms=asset["original_end_ms"],
            duration_ms=asset["duration_ms"],
            url=str(request.base_url).rstrip("/") + f"/v1/playback/{token}",
        ))
    if clips:
        repository.mark_audio_ready(storybook_id)
    return ApiResponse(
        data=StorybookAudioSessionData(
            storybook_id=storybook_id,
            version=context["current_version"],
            source_recording_id=context["source_recording_id"],
            expires_at=min(expiries) if expiries else 0,
            clips=clips,
        ),
        meta=meta_for(request),
    )


@router.post(
    "/storybooks/{storybook_id}/experience-session",
    response_model=ApiResponse[StorybookExperienceSessionData],
    summary="生成连续有声书并签发同步播放地址",
)
def create_storybook_experience_session(
    storybook_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: StorybookRepository = Depends(get_storybook_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
    renderer: StorybookExperienceRenderer = Depends(get_storybook_experience_renderer),
):
    context = repository.get_audio_context(user_id, storybook_id)
    if context is None:
        not_found()
    story_plan = repository.get_story_plan(context["storybook_version_id"])
    if story_plan is None or story_plan["status"] != "CONFIRMED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STORY_PLAN_CONFIRMATION_REQUIRED",
                "message": "请先确认声音故事线，再生成有声绘本",
                "retryable": False,
                "details": {},
            },
        )
    context = {**context, "story_plan": story_plan}
    track = repository.get_experience_track(context["storybook_version_id"])
    if (
        track is None
        or not track.get("object_key")
        or not storage.path_for(track["object_key"]).exists()
    ):
        object_key = (
            f"families/{context['family_id']}/recordings/{context['source_recording_id']}"
            f"/storybooks/{storybook_id}/v{context['current_version']}/experience.mp3"
        )
        try:
            rendered = renderer.render(context, object_key)
        except StorybookExperienceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "STORYBOOK_EXPERIENCE_RENDER_FAILED",
                    "message": str(exc),
                    "retryable": True,
                    "details": {},
                },
            ) from exc
        track = repository.save_experience_track({
            "family_id": context["family_id"],
            "storybook_version_id": context["storybook_version_id"],
            "source_recording_id": context["source_recording_id"],
            "object_key": object_key,
            "duration_ms": rendered["metadata"]["duration_ms"],
            "storyline": rendered["storyline"],
            "cues": rendered["cues"],
            "render_metadata": rendered["metadata"],
        })
        repository.mark_audio_ready(storybook_id)
    token, expires_at = storage.issue_playback_token(
        context["source_recording_id"], track["object_key"], track["media_type"]
    )
    metadata = track["render_metadata"]
    return ApiResponse(
        data=StorybookExperienceSessionData(
            storybook_id=storybook_id,
            version=context["current_version"],
            source_recording_id=context["source_recording_id"],
            duration_ms=track["duration_ms"],
            url=str(request.base_url).rstrip("/") + f"/v1/playback/{token}",
            expires_at=expires_at,
            storyline_schema_version=track["storyline"]["schema_version"],
            scenes=track["storyline"]["scenes"],
            cues=track["cues"],
            narrator_provider=metadata.get("tts_provider"),
            narrator_voice=metadata.get("tts_voice"),
            music_source=metadata.get("music_source"),
        ),
        meta=meta_for(request),
    )

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_contracts import (
    CreatePodcastPlanRequest,
    PodcastNarrationPreviewData,
    PodcastNarrationPreviewRequest,
    PodcastMaterialData,
    PodcastPlanWorkspaceData,
    UpdatePodcastPlanRequest,
)
from .podcast_narrative import (
    InvalidPodcastPlan,
    PodcastNarrativeGenerator,
    OpenAICompatibleNarrativeGenerator,
    ResilientPodcastNarrativeGenerator,
    SafePodcastNarrativeGenerator,
    validate_podcast_plan,
)
from .podcast_audio import SpeechSynthesisError
from .podcast_preview import LocalNarrationPreviewService, NarrationPreviewService
from .podcast_plan_repository import (
    PodcastPlanRepository,
    PostgresPodcastPlanRepository,
)
from .podcast_release import PodcastReleasePolicy


router = APIRouter(prefix="/v1", tags=["podcast-plan"])


def get_podcast_plan_repository() -> PodcastPlanRepository:
    return PostgresPodcastPlanRepository(get_settings().database_url)


def get_narration_preview_service() -> NarrationPreviewService:
    return LocalNarrationPreviewService(get_settings())


def get_podcast_narrative_generator() -> PodcastNarrativeGenerator:
    settings = get_settings()
    safe = SafePodcastNarrativeGenerator(
        provider=settings.podcast_script_provider,
        model_version=settings.podcast_script_model,
    )
    primary = None
    if settings.podcast_script_endpoint and settings.podcast_script_api_key:
        primary = OpenAICompatibleNarrativeGenerator(
            endpoint=settings.podcast_script_endpoint,
            api_key=settings.podcast_script_api_key,
            model_version=settings.podcast_script_model,
            provider=settings.podcast_script_provider,
            timeout_seconds=settings.podcast_script_timeout_seconds,
        )
    return ResilientPodcastNarrativeGenerator(primary=primary, fallback=safe)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def materials_required():
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "PODCAST_MATERIALS_NOT_CONFIRMED",
            "message": "请先确认并锁定声音素材，再生成第三人称串讲草案",
            "retryable": False,
            "details": {},
        },
    )


@router.get(
    "/recordings/{recording_id}/podcast-plan",
    response_model=ApiResponse[PodcastPlanWorkspaceData],
)
def get_podcast_plan(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastPlanRepository = Depends(get_podcast_plan_repository),
):
    context = repository.get_context(user_id, recording_id)
    if context is None:
        materials_required()
    plan = repository.get_plan(user_id, recording_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PODCAST_PLAN_NOT_FOUND",
                "message": "串讲草案尚未生成",
                "retryable": False,
                "details": {},
            },
        )
    return ApiResponse(
        data=PodcastPlanWorkspaceData.model_validate(plan),
        meta=meta_for(request),
    )


@router.post(
    "/recordings/{recording_id}/podcast-plan/draft",
    response_model=ApiResponse[PodcastPlanWorkspaceData],
)
def create_podcast_plan_draft(
    recording_id: UUID,
    body: CreatePodcastPlanRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastPlanRepository = Depends(get_podcast_plan_repository),
    generator: PodcastNarrativeGenerator = Depends(get_podcast_narrative_generator),
):
    if not PodcastReleasePolicy(get_settings()).can_create(user_id):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "PODCAST_CREATION_PAUSED", "message": "家庭播客创建暂未对当前用户开放",
            "retryable": True, "details": {},
        })
    context = repository.get_context(user_id, recording_id)
    if context is None:
        materials_required()
    materials = [PodcastMaterialData.model_validate(item) for item in context["materials"]]
    try:
        plan = generator.generate(
            context["recording_title"], materials, body.narration_style
        )
    except InvalidPodcastPlan as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PODCAST_PLAN_SAFETY_CHECK_FAILED",
                "message": str(exc),
                "retryable": False,
                "details": {},
            },
        ) from exc
    saved = repository.save_plan(user_id, recording_id, plan)
    if saved is None:
        materials_required()
    return ApiResponse(
        data=PodcastPlanWorkspaceData.model_validate(saved),
        meta=meta_for(request),
    )


@router.put(
    "/recordings/{recording_id}/podcast-plan",
    response_model=ApiResponse[PodcastPlanWorkspaceData],
)
def update_podcast_plan(
    recording_id: UUID,
    body: UpdatePodcastPlanRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastPlanRepository = Depends(get_podcast_plan_repository),
):
    current = repository.get_plan(user_id, recording_id)
    if current is None:
        materials_required()
    materials = [PodcastMaterialData.model_validate(item) for item in current["materials"]]
    existing = current["plan"]
    candidate = {
        "title": body.title.strip(),
        "description": body.description.strip(),
        "narrator_voice": body.narrator_voice,
        "music_style": body.music_style,
        "narration_style": existing["narration_style"],
        "generator_provider": existing["generator_provider"],
        "prompt_version": existing["prompt_version"],
        "model_version": existing["model_version"],
        "external_share_allowed": all(item.share_allowed for item in materials),
        "segments": [item.model_dump(mode="json") for item in body.segments],
    }
    try:
        candidate["safety_checks"] = validate_podcast_plan(candidate, materials)
    except InvalidPodcastPlan as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "PODCAST_PLAN_SAFETY_CHECK_FAILED",
                "message": str(exc),
                "retryable": False,
                "details": {},
            },
        ) from exc
    saved = repository.update_plan(user_id, recording_id, body.status, candidate)
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PODCAST_PLAN_ALREADY_CONFIRMED",
                "message": "策划版本已经确认；如需修改，请创建新的声音素材修订",
                "retryable": False,
                "details": {},
            },
        )
    return ApiResponse(
        data=PodcastPlanWorkspaceData.model_validate(saved),
        meta=meta_for(request),
    )


@router.post(
    "/recordings/{recording_id}/podcast-plan/narration-preview",
    response_model=ApiResponse[PodcastNarrationPreviewData],
)
def create_narration_preview(
    recording_id: UUID,
    body: PodcastNarrationPreviewRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastPlanRepository = Depends(get_podcast_plan_repository),
    preview: NarrationPreviewService = Depends(get_narration_preview_service),
):
    context = repository.get_context(user_id, recording_id)
    workspace = repository.get_plan(user_id, recording_id)
    if context is None or workspace is None:
        materials_required()
    segment = next(
        (
            item for item in workspace["plan"]["segments"]
            if item["segment_index"] == body.segment_index and item["kind"] == "narration"
        ),
        None,
    )
    if segment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "NARRATION_SEGMENT_REQUIRED",
                "message": "只能试听 AI 解说段",
                "retryable": False,
                "details": {},
            },
        )
    try:
        result = preview.create(
            recording_id, context["family_id"], segment["text"],
            workspace["plan"]["narrator_voice"],
        )
    except SpeechSynthesisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "NARRATION_PREVIEW_UNAVAILABLE",
                "message": str(exc),
                "retryable": True,
                "details": {},
            },
        ) from exc
    url = str(request.base_url).rstrip("/") + f"/v1/playback/{result['token']}"
    return ApiResponse(
        data=PodcastNarrationPreviewData(
            url=url,
            expires_at=result["expires_at"],
            provider=result["provider"],
            voice=result["voice"],
        ),
        meta=meta_for(request),
    )

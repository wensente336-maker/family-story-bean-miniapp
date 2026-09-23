from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .recording_router import get_object_storage, get_recording_repository
from .repositories import RecordingRepository
from .transcript_contracts import (
    PlaybackUrlData,
    SpeakerMappingData,
    TranscriptData,
    TranscriptSegmentData,
    UpdateSpeakerMappingRequest,
    UpdateTranscriptSegmentRequest,
)
from .transcript_repository import PostgresTranscriptRepository, TranscriptRepository
from .upload_storage import InvalidUploadToken, LocalObjectStorage
from .podcast_share_router import get_podcast_share_repository
from .podcast_share_repository import PodcastShareRepository


router = APIRouter(prefix="/v1", tags=["transcripts"])


def get_transcript_repository() -> TranscriptRepository:
    return PostgresTranscriptRepository(get_settings().database_url)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found(message: str = "转写不存在或无权访问"):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "TRANSCRIPT_NOT_FOUND", "message": message, "retryable": False, "details": {}},
    )


def transcript_payload(raw: dict) -> TranscriptData:
    recording = raw["recording"]
    settings = get_settings()
    return TranscriptData(
        recording_id=recording["id"], title=recording["title"],
        duration_ms=recording["duration_ms"], language=recording.get("transcript_language"),
        asr_provider=recording.get("asr_provider"), asr_model=recording.get("asr_model"),
        revision=recording.get("transcript_revision", 0),
        low_confidence_threshold=settings.asr_low_confidence_threshold,
        speakers=raw["speakers"], family_members=raw["members"], segments=raw["segments"],
    )


@router.get("/recordings/{recording_id}/transcript", response_model=ApiResponse[TranscriptData])
def get_transcript(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: TranscriptRepository = Depends(get_transcript_repository),
):
    raw = repository.get_for_user(user_id, recording_id)
    if raw is None:
        not_found()
    return ApiResponse(data=transcript_payload(raw), meta=meta_for(request))


@router.patch(
    "/recordings/{recording_id}/transcript/segments/{segment_id}",
    response_model=ApiResponse[TranscriptSegmentData],
)
def update_segment(
    recording_id: UUID, segment_id: UUID, body: UpdateTranscriptSegmentRequest,
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: TranscriptRepository = Depends(get_transcript_repository),
):
    segment = repository.update_segment(
        user_id, recording_id, segment_id, body.text, body.speaker_key
    )
    if segment is None:
        not_found("转写片段不存在或无权访问")
    return ApiResponse(data=TranscriptSegmentData.model_validate(segment), meta=meta_for(request))


@router.put(
    "/recordings/{recording_id}/speakers/{speaker_key}",
    response_model=ApiResponse[SpeakerMappingData],
)
def update_speaker(
    recording_id: UUID, speaker_key: str, body: UpdateSpeakerMappingRequest,
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: TranscriptRepository = Depends(get_transcript_repository),
):
    mapping = repository.set_speaker_mapping(
        user_id, recording_id, speaker_key, body.family_member_id, body.display_name
    )
    if mapping is None:
        not_found("说话人或家庭成员不存在")
    return ApiResponse(data=SpeakerMappingData.model_validate(mapping), meta=meta_for(request))


@router.post(
    "/recordings/{recording_id}/playback-url",
    response_model=ApiResponse[PlaybackUrlData],
)
def create_playback_url(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    recordings: RecordingRepository = Depends(get_recording_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    recording = recordings.get_recording(user_id, recording_id)
    if recording is None:
        not_found("录音不存在或无权访问")
    object_key = recording.get("object_key")
    if not object_key or not storage.path_for(object_key).exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "code": "ORIGINAL_AUDIO_PURGED",
                "message": "原始录音已按家庭隐私保留设置清理",
                "retryable": False,
                "details": {},
            },
        )
    token, expires_at = storage.issue_playback_token(
        recording_id, object_key, recording.get("media_type") or "application/octet-stream"
    )
    url = str(request.base_url).rstrip("/") + f"/v1/playback/{token}"
    return ApiResponse(data=PlaybackUrlData(url=url, expires_at=expires_at), meta=meta_for(request))


@router.get("/playback/{token}", response_class=FileResponse)
def playback(
    token: str, download: bool = Query(default=False),
    storage: LocalObjectStorage = Depends(get_object_storage),
    shares: PodcastShareRepository = Depends(get_podcast_share_repository),
):
    try:
        claims = storage.verify_playback_token(token)
        path = storage.path_for(claims.object_key)
    except InvalidUploadToken:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid playback token")
    if claims.share_token:
        share = shares.resolve(claims.share_token, count_access=False)
        if share is None or share["recording_id"] != claims.recording_id or claims.object_key not in {
            share["object_key"], share.get("cover_object_key"),
        }:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share unavailable")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audio not found")
    return FileResponse(
        path, media_type=claims.media_type,
        filename=(
            "family-story-cover.webp" if claims.media_type.startswith("image/")
            else "family-story-podcast.mp3"
        ) if download else None,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store"} if claims.share_token else None,
    )

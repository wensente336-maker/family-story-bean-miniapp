from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse, JobData
from .job_repository import JobRepository
from .job_router import get_job_dispatcher, get_job_repository
from .job_service import CeleryJobDispatcher, QueueUnavailableError
from .media import MediaValidationError, validate_media
from .recording_contracts import (
    CompleteUploadRequest,
    CompleteUploadData,
    CreateRecordingData,
    CreateRecordingRequest,
    DeleteRecordingData,
    RecordingData,
    UploadReceiptData,
    UploadTargetData,
)
from .repositories import PostgresRecordingRepository, RecordingRepository
from .upload_storage import InvalidUploadToken, LocalObjectStorage, UploadTooLarge


router = APIRouter(prefix="/v1", tags=["recordings"])


def get_recording_repository() -> RecordingRepository:
    return PostgresRecordingRepository(get_settings().database_url)


def get_object_storage() -> LocalObjectStorage:
    return LocalObjectStorage(get_settings())


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def api_error(code: str, message: str, status_code: int, *, retryable: bool = False):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": retryable, "details": {}},
    )


@router.post(
    "/recordings", response_model=ApiResponse[CreateRecordingData],
    status_code=status.HTTP_201_CREATED,
)
def create_recording(
    body: CreateRecordingRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: RecordingRepository = Depends(get_recording_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    recording = repository.create_recording(
        user_id, body.title.strip(), body.original_file_name, body.declared_size,
        body.declared_media_type, body.sha256, body.source_type,
    )
    if recording is None:
        api_error("FAMILY_NOT_FOUND", "请先创建家庭", status.HTTP_409_CONFLICT)
    token, expires_at = storage.issue_upload_token(recording["id"], recording["object_key"])
    upload_url = str(request.base_url).rstrip("/") + f"/v1/uploads/{token}"
    return ApiResponse(
        data=CreateRecordingData(
            recording=RecordingData.model_validate(recording),
            upload=UploadTargetData(
                url=upload_url, expires_at=expires_at,
                headers={"Content-Type": "application/octet-stream"},
            ),
        ),
        meta=meta_for(request),
    )


@router.put("/uploads/{token}", response_model=ApiResponse[UploadReceiptData])
async def direct_upload(
    token: str,
    request: Request,
    repository: RecordingRepository = Depends(get_recording_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    try:
        claims = storage.verify_upload_token(token)
    except InvalidUploadToken:
        api_error("UPLOAD_TOKEN_INVALID", "上传凭证无效或已过期", status.HTTP_401_UNAUTHORIZED)
    recording = repository.get_recording_for_upload(claims.recording_id)
    if recording is None or recording["object_key"] != claims.object_key:
        api_error("RECORDING_NOT_FOUND", "录音不存在", status.HTTP_404_NOT_FOUND)
    if str(recording["status"]) not in {"UPLOADING", "FAILED"}:
        api_error("UPLOAD_STATE_INVALID", "当前录音不能重新上传", status.HTTP_409_CONFLICT)
    try:
        size, digest = await storage.put(request, claims.object_key)
    except UploadTooLarge:
        repository.mark_failed(claims.recording_id, "MEDIA_TOO_LARGE")
        api_error("MEDIA_TOO_LARGE", "媒体文件超过允许大小", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    except ValueError:
        repository.mark_failed(claims.recording_id, "MEDIA_EMPTY")
        api_error("MEDIA_EMPTY", "媒体文件为空", status.HTTP_422_UNPROCESSABLE_ENTITY)
    return ApiResponse(
        data=UploadReceiptData(
            recording_id=claims.recording_id, bytes_received=size, sha256=digest
        ),
        meta=meta_for(request),
    )


@router.post(
    "/recordings/{recording_id}/upload-complete",
    response_model=ApiResponse[CompleteUploadData],
)
def complete_upload(
    recording_id: UUID,
    body: CompleteUploadRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: RecordingRepository = Depends(get_recording_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
    job_repository: JobRepository = Depends(get_job_repository),
    dispatcher: CeleryJobDispatcher = Depends(get_job_dispatcher),
):
    recording = repository.get_recording(user_id, recording_id)
    if recording is None:
        api_error("RECORDING_NOT_FOUND", "录音不存在或无权访问", status.HTTP_404_NOT_FOUND)
    post_upload_stages = {
        "UPLOADED", "PREPROCESSING", "TRANSCRIBING", "ANALYZING", "READY_FOR_SELECTION"
    }
    if str(recording["status"]) in post_upload_stages:
        if recording["sha256"] != body.sha256:
            api_error("UPLOAD_ALREADY_COMPLETED", "该录音已完成上传", status.HTTP_409_CONFLICT)
        job = job_repository.create_for_recording(
            user_id, recording_id, get_settings().pipeline_version
        )
        if job is None:
            api_error("JOB_CREATE_FAILED", "无法创建处理任务", status.HTTP_409_CONFLICT)
        if str(job["stage"]) == "CREATED":
            try:
                dispatcher.enqueue(job["id"])
            except QueueUnavailableError:
                pass
            job = job_repository.get_for_user(user_id, job["id"]) or job
        return ApiResponse(
            data=CompleteUploadData(
                recording=RecordingData.model_validate(recording),
                job=JobData.model_validate(job),
            ),
            meta=meta_for(request),
        )
    if recording["sha256"] != body.sha256:
        repository.mark_failed(recording_id, "AUDIO_CHECKSUM_MISMATCH")
        api_error(
            "AUDIO_CHECKSUM_MISMATCH",
            "完成回调的音频摘要与创建记录时不一致",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        info = validate_media(storage.path_for(recording["object_key"]), body.sha256)
    except MediaValidationError as exc:
        repository.mark_failed(recording_id, exc.code)
        api_error(exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    completed = repository.mark_uploaded(
        user_id, recording_id, info.media_type, info.duration_ms, info.file_size, info.sha256
    )
    if completed is None:
        api_error("RECORDING_NOT_FOUND", "录音不存在或无权访问", status.HTTP_404_NOT_FOUND)
    job = job_repository.create_for_recording(
        user_id, recording_id, get_settings().pipeline_version
    )
    if job is None:
        api_error("JOB_CREATE_FAILED", "无法创建处理任务", status.HTTP_409_CONFLICT)
    try:
        dispatcher.enqueue(job["id"])
    except QueueUnavailableError:
        pass
    job = job_repository.get_for_user(user_id, job["id"]) or job
    return ApiResponse(
        data=CompleteUploadData(
            recording=RecordingData.model_validate(completed),
            job=JobData.model_validate(job),
        ),
        meta=meta_for(request),
    )


@router.get("/recordings", response_model=ApiResponse[list[RecordingData]])
def list_recordings(
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: RecordingRepository = Depends(get_recording_repository),
):
    return ApiResponse(
        data=[RecordingData.model_validate(item) for item in repository.list_recordings(user_id)],
        meta=meta_for(request),
    )


@router.get("/recordings/{recording_id}", response_model=ApiResponse[RecordingData])
def get_recording(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: RecordingRepository = Depends(get_recording_repository),
):
    recording = repository.get_recording(user_id, recording_id)
    if recording is None:
        api_error("RECORDING_NOT_FOUND", "录音不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=RecordingData.model_validate(recording), meta=meta_for(request))


@router.delete(
    "/recordings/{recording_id}", response_model=ApiResponse[DeleteRecordingData]
)
def delete_recording_draft(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: RecordingRepository = Depends(get_recording_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    recording = repository.delete_draft(user_id, recording_id)
    if recording is None:
        api_error("DRAFT_NOT_FOUND", "草稿不存在、无权访问或已进入处理", status.HTTP_404_NOT_FOUND)
    storage.delete(recording["object_key"])
    return ApiResponse(data=DeleteRecordingData(id=recording_id), meta=meta_for(request))

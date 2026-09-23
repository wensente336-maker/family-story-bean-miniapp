from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse, JobData
from .job_repository import JobRepository, PostgresJobRepository
from .job_service import CeleryJobDispatcher, QueueUnavailableError


router = APIRouter(prefix="/v1", tags=["jobs"])


class PipelineStatusData(BaseModel):
    accepting_new_jobs: bool
    stale_after_seconds: int
    max_automatic_retries: int = 2


def get_job_repository() -> JobRepository:
    return PostgresJobRepository(get_settings().database_url)


def get_job_dispatcher(
    repository: JobRepository = Depends(get_job_repository),
) -> CeleryJobDispatcher:
    return CeleryJobDispatcher(get_settings(), repository)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def job_not_found():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "JOB_NOT_FOUND", "message": "任务不存在或无权访问",
            "retryable": False, "details": {},
        },
    )


def opportunistic_enqueue(job: dict, dispatcher: CeleryJobDispatcher) -> None:
    if str(job["stage"]) != "CREATED":
        return
    last_attempt = job.get("queue_attempted_at")
    if last_attempt is not None:
        # A successful broker submission is durable; polling must not publish the
        # same Celery task every two seconds while no worker is online. Failed
        # broker submissions may be retried, but are throttled to avoid a storm.
        if not job.get("error_code"):
            return
        if datetime.now(UTC) - last_attempt < timedelta(seconds=10):
            return
    try:
        dispatcher.enqueue(job["id"])
    except QueueUnavailableError:
        pass


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobData])
def get_job(
    job_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: JobRepository = Depends(get_job_repository),
    dispatcher: CeleryJobDispatcher = Depends(get_job_dispatcher),
):
    job = repository.get_for_user(user_id, job_id)
    if job is None:
        job_not_found()
    opportunistic_enqueue(job, dispatcher)
    refreshed = repository.get_for_user(user_id, job_id) or job
    return ApiResponse(data=JobData.model_validate(refreshed), meta=meta_for(request))


@router.get("/recordings/{recording_id}/job", response_model=ApiResponse[JobData])
def get_recording_job(
    recording_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: JobRepository = Depends(get_job_repository),
    dispatcher: CeleryJobDispatcher = Depends(get_job_dispatcher),
):
    job = repository.get_by_recording_for_user(user_id, recording_id)
    if job is None:
        job_not_found()
    opportunistic_enqueue(job, dispatcher)
    refreshed = repository.get_for_user(user_id, job["id"]) or job
    return ApiResponse(data=JobData.model_validate(refreshed), meta=meta_for(request))


@router.post("/jobs/{job_id}/retry", response_model=ApiResponse[JobData])
def retry_job(
    job_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: JobRepository = Depends(get_job_repository),
    dispatcher: CeleryJobDispatcher = Depends(get_job_dispatcher),
):
    job = repository.reset_for_manual_retry(user_id, job_id)
    if job is None:
        job_not_found()
    try:
        dispatcher.enqueue(job_id)
    except QueueUnavailableError:
        pass
    refreshed = repository.get_for_user(user_id, job_id) or job
    return ApiResponse(data=JobData.model_validate(refreshed), meta=meta_for(request))


@router.get("/pipeline/status", response_model=ApiResponse[PipelineStatusData])
def pipeline_status(request: Request, _user_id: UUID = Depends(current_user_id)):
    settings = get_settings()
    return ApiResponse(
        data=PipelineStatusData(
            accepting_new_jobs=settings.pipeline_accept_new_jobs,
            stale_after_seconds=settings.pipeline_stale_after_seconds,
        ),
        meta=meta_for(request),
    )

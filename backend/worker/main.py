from __future__ import annotations

import time
from contextlib import contextmanager
from threading import Event, Thread
from uuid import UUID

from celery import Celery

from app.config import get_settings
from app.job_repository import PostgresJobRepository
from app.moment_discovery import MomentDiscoveryService
from app.moment_repository import PostgresMomentRepository
from app.transcript_repository import PostgresTranscriptRepository
from app.transcription import AsrConfigurationError, RecordingTranscriptionPipeline
from app.upload_storage import LocalObjectStorage
from app.lifecycle_repository import PostgresLifecycleRepository
from app.podcast_audio import LocalPodcastRenderer
from app.podcast_render_repository import PostgresPodcastRenderRepository
from app.podcast_render_service import PodcastRenderService


settings = get_settings()
celery_app = Celery(
    "family_story_bean",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


@contextmanager
def lease_heartbeat(repository, job_id: UUID, execution_token: str):
    stopped = Event()
    interval = max(5.0, settings.pipeline_stale_after_seconds / 3)

    def pulse():
        while not stopped.wait(interval):
            repository.heartbeat(job_id, execution_token)

    thread = Thread(target=pulse, name=f"heartbeat-{job_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": settings.pipeline_task_time_limit_seconds * 2},
    task_routes={
        "pipeline.process_recording": {"queue": "pipeline"},
        "pipeline.dead_letter": {"queue": "pipeline.dead"},
        "pipeline.recover_stale": {"queue": "pipeline.maintenance"},
        "privacy.purge_expired_originals": {"queue": "pipeline.maintenance"},
        "podcast.render": {"queue": "podcast"},
    },
    beat_schedule={
        "recover-stale-recording-jobs": {
            "task": "pipeline.recover_stale",
            "schedule": 30.0,
        },
        "purge-expired-original-recordings": {
            "task": "privacy.purge_expired_originals",
            "schedule": 3600.0,
        },
    },
)


@celery_app.task(
    name="podcast.render",
    bind=True,
    max_retries=settings.podcast_render_max_retries,
    soft_time_limit=settings.pipeline_task_time_limit_seconds - 30,
    time_limit=settings.pipeline_task_time_limit_seconds,
)
def render_podcast(self, job_id: str):
    repository = PostgresPodcastRenderRepository(settings.database_url)
    service = PodcastRenderService(repository, LocalPodcastRenderer(settings))
    result = service.run(UUID(job_id))
    if result.get("status") == "FAILED" and self.request.retries < settings.podcast_render_max_retries:
        raise self.retry(
            exc=RuntimeError(result.get("error") or "podcast render failed"),
            countdown=min(2 ** self.request.retries, 30),
        )
    return result


def run_pipeline(
    job_id: UUID,
    execution_token: str,
    repository: PostgresJobRepository,
    *,
    sleeper=time.sleep,
    fault_stage: str | None = None,
    transcription_pipeline: RecordingTranscriptionPipeline | None = None,
    moment_pipeline: MomentDiscoveryService | None = None,
) -> dict[str, str | int]:
    job = repository.claim(job_id, execution_token, settings.pipeline_stale_after_seconds)
    if job is None:
        return {"job_id": str(job_id), "status": "DUPLICATE_SKIPPED", "progress": 100}

    for stage, progress in (("PREPROCESSING", 25),):
        if fault_stage == stage and settings.allow_task_fault_injection:
            raise RuntimeError(f"fault injection at {stage}")
        sleeper(settings.pipeline_demo_step_seconds)
        updated = repository.update_stage(job_id, execution_token, stage, progress)
        if updated is None:
            return {"job_id": str(job_id), "status": "LEASE_LOST", "progress": progress}
    if fault_stage == "TRANSCRIBING" and settings.allow_task_fault_injection:
        raise RuntimeError("fault injection at TRANSCRIBING")
    repository.update_stage(job_id, execution_token, "TRANSCRIBING", 40)
    if transcription_pipeline is not None:
        with lease_heartbeat(repository, job_id, execution_token):
            transcription_pipeline.process(job["recording_id"])
        repository.update_stage(job_id, execution_token, "TRANSCRIBING", 65)
    else:
        sleeper(settings.pipeline_demo_step_seconds)
        repository.update_stage(job_id, execution_token, "TRANSCRIBING", 50)
    if fault_stage == "ANALYZING" and settings.allow_task_fault_injection:
        raise RuntimeError("fault injection at ANALYZING")
    updated = repository.update_stage(job_id, execution_token, "ANALYZING", 75)
    if updated is None:
        return {"job_id": str(job_id), "status": "LEASE_LOST", "progress": 75}
    if moment_pipeline is not None:
        with lease_heartbeat(repository, job_id, execution_token):
            moment_pipeline.process(job["recording_id"])
    else:
        sleeper(settings.pipeline_demo_step_seconds)
    if fault_stage == "READY_FOR_SELECTION" and settings.allow_task_fault_injection:
        raise RuntimeError("fault injection at READY_FOR_SELECTION")
    updated = repository.update_stage(job_id, execution_token, "READY_FOR_SELECTION", 100)
    if updated is None:
        return {"job_id": str(job_id), "status": "LEASE_LOST", "progress": 100}
    return {"job_id": str(job_id), "status": "READY_FOR_SELECTION", "progress": 100}


@celery_app.task(
    name="pipeline.process_recording",
    bind=True,
    max_retries=2,
    soft_time_limit=settings.pipeline_task_time_limit_seconds - 30,
    time_limit=settings.pipeline_task_time_limit_seconds,
)
def process_recording(self, job_id: str, fault_stage: str | None = None):
    repository = PostgresJobRepository(settings.database_url)
    transcription_pipeline = RecordingTranscriptionPipeline(
        settings,
        PostgresTranscriptRepository(settings.database_url),
        LocalObjectStorage(settings),
    )
    moment_pipeline = MomentDiscoveryService(
        PostgresMomentRepository(settings.database_url), settings.pipeline_version
    )
    execution_token = self.request.id or f"worker-{job_id}"
    try:
        return run_pipeline(
            UUID(job_id), execution_token, repository, fault_stage=fault_stage,
            transcription_pipeline=transcription_pipeline,
            moment_pipeline=moment_pipeline,
        )
    except Exception as exc:
        if isinstance(exc, AsrConfigurationError):
            error_code = "ASR_MODEL_UNAVAILABLE"
        else:
            current = repository.get_internal(UUID(job_id))
            error_code = "MOMENT_ANALYSIS_FAILED" if current and current.get("stage") == "ANALYZING" else "TRANSCRIPTION_FAILED"
        failed = repository.record_failure(
            UUID(job_id), execution_token, error_code, str(exc)
        )
        if failed and failed.get("dead_lettered_at"):
            dead_letter.apply_async(args=[job_id, failed["error_code"]], queue="pipeline.dead")
            raise
        raise self.retry(exc=exc, countdown=min(2 ** self.request.retries, 30))


@celery_app.task(name="pipeline.dead_letter")
def dead_letter(job_id: str, error_code: str) -> dict[str, str]:
    return {"job_id": job_id, "error_code": error_code, "status": "DEAD_LETTERED"}


@celery_app.task(name="pipeline.recover_stale")
def recover_stale() -> dict[str, int]:
    repository = PostgresJobRepository(settings.database_url)
    recovered_ids = repository.recover_stale(settings.pipeline_stale_after_seconds)
    for job_id in recovered_ids:
        job = repository.get_internal(job_id)
        if job and not job.get("dead_lettered_at"):
            process_recording.apply_async(
                args=[str(job_id)], queue="pipeline", task_id=f"recording-pipeline-{job_id}"
            )
    return {"recovered": len(recovered_ids)}


@celery_app.task(name="privacy.purge_expired_originals")
def purge_expired_originals() -> dict[str, int]:
    repository = PostgresLifecycleRepository(
        settings.database_url, LocalObjectStorage(settings)
    )
    return repository.purge_expired_originals()


@celery_app.task(name="pipeline.contract_smoke", bind=True, max_retries=2)
def contract_smoke(self, recording_id: str) -> dict[str, str]:
    return {
        "recording_id": recording_id,
        "pipeline_version": settings.pipeline_version,
        "status": "CONTRACT_OK",
    }

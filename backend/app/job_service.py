from __future__ import annotations

from uuid import UUID

from .config import Settings
from .job_repository import JobRepository


class QueueUnavailableError(RuntimeError):
    pass


class CeleryJobDispatcher:
    def __init__(self, settings: Settings, repository: JobRepository):
        self.settings = settings
        self.repository = repository

    def enqueue(self, job_id: UUID) -> bool:
        if not self.settings.pipeline_accept_new_jobs:
            self.repository.mark_queue_attempt(job_id, "PIPELINE_PAUSED")
            return False
        try:
            from worker.main import process_recording

            process_recording.apply_async(
                args=[str(job_id)],
                task_id=f"recording-pipeline-{job_id}",
                queue="pipeline",
            )
            self.repository.mark_queue_attempt(job_id)
            return True
        except Exception as exc:
            self.repository.mark_queue_attempt(job_id, "QUEUE_UNAVAILABLE")
            raise QueueUnavailableError("task queue unavailable") from exc

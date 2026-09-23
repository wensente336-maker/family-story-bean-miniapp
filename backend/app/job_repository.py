from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ACTIVE_STAGES = ("PREPROCESSING", "TRANSCRIBING", "ANALYZING", "GENERATING")


class JobRepository(Protocol):
    def create_for_recording(self, user_id: UUID, recording_id: UUID, pipeline_version: str) -> dict | None: ...
    def get_for_user(self, user_id: UUID, job_id: UUID) -> dict | None: ...
    def get_by_recording_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def latest_for_user(self, user_id: UUID) -> dict | None: ...
    def get_internal(self, job_id: UUID) -> dict | None: ...
    def mark_queue_attempt(self, job_id: UUID, error_code: str | None = None) -> None: ...
    def claim(self, job_id: UUID, execution_token: str, stale_after_seconds: int) -> dict | None: ...
    def update_stage(self, job_id: UUID, execution_token: str, stage: str, progress: int) -> dict | None: ...
    def heartbeat(self, job_id: UUID, execution_token: str) -> None: ...
    def record_failure(self, job_id: UUID, execution_token: str, error_code: str, detail: str) -> dict | None: ...
    def reset_for_manual_retry(self, user_id: UUID, job_id: UUID) -> dict | None: ...
    def recover_stale(self, stale_after_seconds: int) -> list[UUID]: ...


class PostgresJobRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_for_recording(
        self, user_id: UUID, recording_id: UUID, pipeline_version: str
    ) -> dict | None:
        key = f"{recording_id}:RECORDING_PIPELINE:{pipeline_version}"
        with self._connect() as connection:
            recording = connection.execute(
                """
                SELECT recording.id, recording.family_id
                FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE recording.id = %s AND family.owner_user_id = %s
                  AND recording.status IN (
                    'UPLOADED', 'PREPROCESSING', 'TRANSCRIBING', 'ANALYZING',
                    'READY_FOR_SELECTION'
                  )
                """,
                (recording_id, user_id),
            ).fetchone()
            if recording is None:
                return None
            return connection.execute(
                """
                INSERT INTO jobs (
                  family_id, recording_id, type, stage, progress,
                  idempotency_key, pipeline_version
                ) VALUES (%s, %s, 'RECORDING_PIPELINE', 'CREATED', 0, %s, %s)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key = EXCLUDED.idempotency_key
                RETURNING *
                """,
                (recording["family_id"], recording_id, key, pipeline_version),
            ).fetchone()

    def get_for_user(self, user_id: UUID, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT job.* FROM jobs AS job
                JOIN families AS family ON family.id = job.family_id
                WHERE job.id = %s AND family.owner_user_id = %s
                """,
                (job_id, user_id),
            ).fetchone()

    def get_by_recording_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT job.* FROM jobs AS job
                JOIN families AS family ON family.id = job.family_id
                WHERE job.recording_id = %s AND family.owner_user_id = %s
                ORDER BY job.created_at DESC LIMIT 1
                """,
                (recording_id, user_id),
            ).fetchone()

    def latest_for_user(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT job.* FROM jobs AS job
                JOIN families AS family ON family.id = job.family_id
                WHERE family.owner_user_id = %s
                ORDER BY job.created_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()

    def get_internal(self, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()

    def mark_queue_attempt(self, job_id: UUID, error_code: str | None = None) -> None:
        error_detail = (
            {} if error_code is None else {"message": "任务队列暂时不可用"}
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET queue_attempted_at = now(), error_code = %s,
                  error_detail = %s,
                  updated_at = now()
                WHERE id = %s AND stage = 'CREATED'
                """,
                (error_code, Jsonb(error_detail), job_id),
            )

    def claim(self, job_id: UUID, execution_token: str, stale_after_seconds: int) -> dict | None:
        stale_before = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE jobs SET stage = 'PREPROCESSING', progress = GREATEST(progress, 10),
                  execution_token = %s, heartbeat_at = now(), started_at = COALESCE(started_at, now()),
                  error_code = NULL, error_detail = '{}'::jsonb, updated_at = now()
                WHERE id = %s AND dead_lettered_at IS NULL AND (
                  stage = 'CREATED'
                  OR (stage = 'FAILED' AND retry_count <= 2)
                  OR (stage IN ('PREPROCESSING','TRANSCRIBING','ANALYZING') AND execution_token = %s)
                  OR (stage IN ('PREPROCESSING','TRANSCRIBING','ANALYZING') AND heartbeat_at < %s)
                )
                RETURNING *
                """,
                (execution_token, job_id, execution_token, stale_before),
            ).fetchone()
            if job:
                connection.execute(
                    "UPDATE recordings SET status = 'PREPROCESSING', updated_at = now() WHERE id = %s",
                    (job["recording_id"],),
                )
            return job

    def update_stage(
        self, job_id: UUID, execution_token: str, stage: str, progress: int
    ) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE jobs SET stage = %s, progress = %s, heartbeat_at = now(),
                  completed_at = CASE WHEN %s IN ('READY_FOR_SELECTION','COMPLETED') THEN now()
                    ELSE completed_at END,
                  updated_at = now()
                WHERE id = %s AND execution_token = %s
                RETURNING *
                """,
                (stage, progress, stage, job_id, execution_token),
            ).fetchone()
            if job:
                connection.execute(
                    "UPDATE recordings SET status = %s, updated_at = now() WHERE id = %s",
                    (stage, job["recording_id"]),
                )
            return job

    def heartbeat(self, job_id: UUID, execution_token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET heartbeat_at = now(), updated_at = now()
                WHERE id = %s AND execution_token = %s
                  AND stage IN ('PREPROCESSING','TRANSCRIBING','ANALYZING','GENERATING')
                """,
                (job_id, execution_token),
            )

    def record_failure(
        self, job_id: UUID, execution_token: str, error_code: str, detail: str
    ) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE jobs SET stage = 'FAILED', retry_count = retry_count + 1,
                  error_code = %s, error_detail = jsonb_build_object('message', %s),
                  heartbeat_at = now(),
                  dead_lettered_at = CASE WHEN retry_count + 1 > 2 THEN now()
                    ELSE dead_lettered_at END,
                  updated_at = now()
                WHERE id = %s AND execution_token = %s
                RETURNING *
                """,
                (error_code, detail[:500], job_id, execution_token),
            ).fetchone()
            if job:
                connection.execute(
                    "UPDATE recordings SET status = 'FAILED', error_code = %s, updated_at = now() WHERE id = %s",
                    (error_code, job["recording_id"]),
                )
            return job

    def reset_for_manual_retry(self, user_id: UUID, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE jobs AS job SET stage = 'CREATED', progress = 0, retry_count = 0,
                  error_code = NULL, error_detail = '{}'::jsonb, execution_token = NULL,
                  dead_lettered_at = NULL, completed_at = NULL, updated_at = now()
                FROM families AS family
                WHERE job.id = %s AND family.id = job.family_id
                  AND family.owner_user_id = %s AND job.stage = 'FAILED'
                RETURNING job.*
                """,
                (job_id, user_id),
            ).fetchone()
            if job:
                connection.execute(
                    "UPDATE recordings SET status = 'UPLOADED', error_code = NULL, updated_at = now() WHERE id = %s",
                    (job["recording_id"],),
                )
            return job

    def recover_stale(self, stale_after_seconds: int) -> list[UUID]:
        stale_before = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
        with self._connect() as connection:
            rows = connection.execute(
                """
                UPDATE jobs SET stage = 'FAILED', retry_count = retry_count + 1,
                  error_code = 'WORKER_HEARTBEAT_TIMEOUT',
                  error_detail = '{"message":"Worker 心跳超时，任务将自动恢复"}'::jsonb,
                  dead_lettered_at = CASE WHEN retry_count + 1 > 2 THEN now()
                    ELSE dead_lettered_at END,
                  updated_at = now()
                WHERE stage IN ('PREPROCESSING','TRANSCRIBING','ANALYZING','GENERATING')
                  AND heartbeat_at < %s
                RETURNING id
                """,
                (stale_before,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE recordings AS recording SET status = 'FAILED',
                      error_code = 'WORKER_HEARTBEAT_TIMEOUT', updated_at = now()
                    FROM jobs AS job
                    WHERE job.id = %s AND recording.id = job.recording_id
                    """,
                    (row["id"],),
                )
            return [row["id"] for row in rows]

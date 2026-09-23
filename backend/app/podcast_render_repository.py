from __future__ import annotations

import hashlib
import json
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PodcastRenderRepository(Protocol):
    def create_job(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def get_for_user(self, user_id: UUID, job_id: UUID) -> dict | None: ...
    def get_by_recording(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def load_context(self, job_id: UUID) -> dict | None: ...
    def claim(self, job_id: UUID, execution_token: str) -> dict | None: ...
    def update_progress(self, job_id: UUID, execution_token: str, progress: int) -> None: ...
    def complete(self, job_id: UUID, execution_token: str, object_key: str, metadata: dict) -> dict | None: ...
    def fail(self, job_id: UUID, execution_token: str, code: str, detail: str) -> dict | None: ...
    def reset_for_retry(self, user_id: UUID, job_id: UUID) -> dict | None: ...


class PostgresPodcastRenderRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _result(connection, job: dict) -> dict:
        version = connection.execute(
            "SELECT object_key, render_metadata FROM podcast_versions WHERE id=%s",
            (job["podcast_version_id"],),
        ).fetchone()
        return {
            "job": job,
            "podcast_version_id": job["podcast_version_id"],
            "object_key": version["object_key"],
            "render_metadata": version["render_metadata"] or {},
        }

    def create_job(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT version.id AS podcast_version_id, version.family_id,
                       version.version, plan.id AS plan_id, plan.revision AS plan_revision,
                       material_set.revision AS material_revision, plan.plan
                FROM podcast_versions version
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN podcast_plans plan ON plan.podcast_version_id=version.id
                JOIN podcast_material_sets material_set
                  ON material_set.podcast_version_id=version.id
                JOIN families family ON family.id=version.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                  AND project.deleted_at IS NULL
                  AND version.status IN ('CONFIRMED','GENERATING','COMPLETED','FAILED')
                  AND plan.status='CONFIRMED' AND material_set.status='CONFIRMED'
                ORDER BY version.version DESC LIMIT 1
                """,
                (recording_id, user_id),
            ).fetchone()
            if row is None:
                return None
            fingerprint_source = json.dumps({
                "version_id": str(row["podcast_version_id"]),
                "plan_id": str(row["plan_id"]),
                "plan_revision": row["plan_revision"],
                "material_revision": row["material_revision"],
                "voice": row["plan"].get("narrator_voice"),
                "music": row["plan"].get("music_style"),
            }, sort_keys=True)
            fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
            job = connection.execute(
                """
                INSERT INTO podcast_render_jobs (
                  family_id, podcast_version_id, idempotency_key
                ) VALUES (%s,%s,%s)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key=EXCLUDED.idempotency_key
                RETURNING *
                """,
                (row["family_id"], row["podcast_version_id"], fingerprint),
            ).fetchone()
            return self._result(connection, job)

    def get_for_user(self, user_id: UUID, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                SELECT job.* FROM podcast_render_jobs job
                JOIN podcast_versions version ON version.id=job.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN families family ON family.id=job.family_id
                WHERE job.id=%s AND family.owner_user_id=%s
                  AND project.deleted_at IS NULL
                """,
                (job_id, user_id),
            ).fetchone()
            return self._result(connection, job) if job else None

    def get_by_recording(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                SELECT job.* FROM podcast_render_jobs job
                JOIN podcast_versions version ON version.id=job.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN families family ON family.id=job.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                  AND project.deleted_at IS NULL
                ORDER BY version.version DESC LIMIT 1
                """,
                (recording_id, user_id),
            ).fetchone()
            return self._result(connection, job) if job else None

    def load_context(self, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            context = connection.execute(
                """
                SELECT job.id AS job_id, job.family_id, job.podcast_version_id,
                       job.idempotency_key, version.version, version.narrator_voice,
                       version.music_style, recording.id AS recording_id,
                       recording.object_key AS source_object_key, plan.plan,
                       plan.revision AS plan_revision, material_set.id AS material_set_id
                FROM podcast_render_jobs job
                JOIN podcast_versions version ON version.id=job.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN recordings recording ON recording.id=project.recording_id
                JOIN podcast_plans plan ON plan.podcast_version_id=version.id
                JOIN podcast_material_sets material_set
                  ON material_set.podcast_version_id=version.id
                WHERE job.id=%s AND plan.status='CONFIRMED'
                  AND project.deleted_at IS NULL
                  AND material_set.status='CONFIRMED'
                """,
                (job_id,),
            ).fetchone()
            if context is None:
                return None
            materials = connection.execute(
                """
                SELECT id, source_segment_id, start_ms, end_ms, confirmed_text,
                       speaker_label, position
                FROM podcast_materials WHERE material_set_id=%s ORDER BY position
                """,
                (context["material_set_id"],),
            ).fetchall()
            return {**context, "materials": materials}

    def claim(self, job_id: UUID, execution_token: str) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE podcast_render_jobs
                SET status='GENERATING', progress=GREATEST(progress,5),
                    execution_token=%s, heartbeat_at=now(),
                    started_at=COALESCE(started_at,now()), error_code=NULL,
                    error_detail='{}'::jsonb, updated_at=now()
                WHERE id=%s AND status IN ('CREATED','FAILED')
                RETURNING *
                """,
                (execution_token, job_id),
            ).fetchone()
            if job:
                connection.execute(
                    """
                    UPDATE podcast_versions SET status='GENERATING',
                      render_started_at=COALESCE(render_started_at,now()), updated_at=now()
                    WHERE id=%s
                    """,
                    (job["podcast_version_id"],),
                )
            return job

    def update_progress(self, job_id: UUID, execution_token: str, progress: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE podcast_render_jobs SET progress=%s, heartbeat_at=now(), updated_at=now()
                WHERE id=%s AND execution_token=%s AND status='GENERATING'
                """,
                (progress, job_id, execution_token),
            )

    def complete(self, job_id, execution_token, object_key, metadata):
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE podcast_render_jobs SET status='COMPLETED', progress=100,
                  heartbeat_at=now(), completed_at=now(), updated_at=now()
                WHERE id=%s AND execution_token=%s AND status='GENERATING'
                RETURNING *
                """,
                (job_id, execution_token),
            ).fetchone()
            if job is None:
                return None
            connection.execute(
                """
                UPDATE podcast_versions SET status='COMPLETED', object_key=%s,
                  render_metadata=%s, render_fingerprint=%s, completed_at=now(),
                  failure_code=NULL, failure_detail='{}'::jsonb, updated_at=now()
                WHERE id=%s
                """,
                (object_key, Jsonb(metadata), job["idempotency_key"], job["podcast_version_id"]),
            )
            connection.execute(
                """
                UPDATE podcast_projects project SET current_version=version.version,
                  updated_at=now()
                FROM podcast_versions version
                WHERE version.id=%s AND project.id=version.project_id
                """,
                (job["podcast_version_id"],),
            )
            return self._result(connection, job)

    def fail(self, job_id, execution_token, code, detail):
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE podcast_render_jobs SET status='FAILED',
                  retry_count=retry_count+1, error_code=%s,
                  error_detail=jsonb_build_object('message',%s),
                  heartbeat_at=now(), updated_at=now()
                WHERE id=%s AND execution_token=%s RETURNING *
                """,
                (code, detail[:500], job_id, execution_token),
            ).fetchone()
            if job:
                connection.execute(
                    """
                    UPDATE podcast_versions SET status='FAILED', failure_code=%s,
                      failure_detail=jsonb_build_object('message',%s), updated_at=now()
                    WHERE id=%s
                    """,
                    (code, detail[:500], job["podcast_version_id"]),
                )
                return self._result(connection, job)
            return None

    def reset_for_retry(self, user_id: UUID, job_id: UUID) -> dict | None:
        with self._connect() as connection:
            job = connection.execute(
                """
                UPDATE podcast_render_jobs job SET status='CREATED', progress=0,
                  error_code=NULL, error_detail='{}'::jsonb, execution_token=NULL,
                  completed_at=NULL, updated_at=now()
                FROM families family
                WHERE job.id=%s AND family.id=job.family_id
                  AND family.owner_user_id=%s AND job.status='FAILED'
                RETURNING job.*
                """,
                (job_id, user_id),
            ).fetchone()
            if job:
                connection.execute(
                    """
                    UPDATE podcast_versions SET status='CONFIRMED', failure_code=NULL,
                      failure_detail='{}'::jsonb, updated_at=now()
                    WHERE id=%s
                    """,
                    (job["podcast_version_id"],),
                )
                return self._result(connection, job)
            return None

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .config import Settings


class PodcastReleasePolicy:
    """Pure release gate: reads configuration but never blocks existing assets."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _included(self, user_id: UUID) -> bool:
        mode = self.settings.podcast_rollout_mode.strip().lower()
        if mode == "open":
            return True
        if mode == "off":
            return False
        allowed = {
            item.strip() for item in self.settings.podcast_rollout_user_ids.split(",")
            if item.strip()
        }
        return mode == "allowlist" and str(user_id) in allowed

    def can_create(self, user_id: UUID) -> bool:
        return self.settings.podcast_creation_enabled and self._included(user_id)

    def can_share(self, user_id: UUID) -> bool:
        return self.settings.podcast_sharing_enabled and self._included(user_id)


class PodcastReleaseRepository(Protocol):
    def metrics(self, user_id: UUID) -> dict | None: ...
    def rollback(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def revoke_all_shares(self, user_id: UUID) -> int: ...


class PostgresPodcastReleaseRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def metrics(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                "SELECT id FROM families WHERE owner_user_id=%s ORDER BY created_at LIMIT 1",
                (user_id,),
            ).fetchone()
            if family is None:
                return None
            jobs = connection.execute(
                """
                SELECT count(*) AS total,
                  count(*) FILTER (WHERE job.status='COMPLETED') AS completed,
                  count(*) FILTER (WHERE job.status='FAILED') AS failed,
                  count(*) FILTER (WHERE job.status='COMPLETED' AND job.retry_count=0
                    AND version.render_metadata->>'render_mode'='narrated') AS first_pass,
                  count(*) FILTER (WHERE job.status='COMPLETED') AS usable,
                  count(*) FILTER (WHERE version.render_metadata->>'render_mode'='original_only'
                    OR COALESCE((version.render_metadata->>'tts_fallback_used')::boolean,false)) AS degraded,
                  percentile_cont(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (job.completed_at-job.started_at))
                  ) FILTER (WHERE job.completed_at IS NOT NULL AND job.started_at IS NOT NULL) AS p95
                FROM podcast_render_jobs job
                JOIN podcast_versions version ON version.id=job.podcast_version_id
                WHERE job.family_id=%s
                """,
                (family["id"],),
            ).fetchone()
            failures = connection.execute(
                """
                SELECT COALESCE(error_code,'UNKNOWN') AS code,count(*) AS count
                FROM podcast_render_jobs WHERE family_id=%s AND status='FAILED'
                GROUP BY COALESCE(error_code,'UNKNOWN') ORDER BY count(*) DESC
                """,
                (family["id"],),
            ).fetchall()
            shares = connection.execute(
                """
                SELECT count(*) FILTER (WHERE revoked_at IS NULL AND expires_at>now()) AS active,
                       COALESCE(sum(access_count),0) AS accesses
                FROM podcast_shares WHERE family_id=%s
                """,
                (family["id"],),
            ).fetchone()
            total = int(jobs["total"] or 0)
            completed = int(jobs["completed"] or 0)
            first_pass = int(jobs["first_pass"] or 0)
            degraded = int(jobs["degraded"] or 0)
            return {
                "generation_total": total,
                "generation_completed": completed,
                "generation_failed": int(jobs["failed"] or 0),
                "first_pass_success_rate": first_pass / total if total else None,
                "usable_product_rate": int(jobs["usable"] or 0) / total if total else None,
                "degradation_rate": degraded / total if total else None,
                "generation_p95_seconds": float(jobs["p95"]) if jobs["p95"] is not None else None,
                "failure_reasons": {item["code"]: int(item["count"]) for item in failures},
                "active_shares": int(shares["active"] or 0),
                "share_accesses": int(shares["accesses"] or 0),
            }

    def rollback(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            project = connection.execute(
                """
                SELECT project.id,project.current_version FROM podcast_projects project
                JOIN families family ON family.id=project.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                FOR UPDATE
                """,
                (recording_id, user_id),
            ).fetchone()
            if project is None:
                return None
            active = connection.execute(
                """
                SELECT id,version FROM podcast_versions
                WHERE project_id=%s AND status='COMPLETED' AND object_key IS NOT NULL
                ORDER BY (version=%s) DESC,version DESC LIMIT 1
                """,
                (project["id"], project["current_version"]),
            ).fetchone()
            if active is None:
                return None
            target = connection.execute(
                """
                SELECT id,version,object_key FROM podcast_versions
                WHERE project_id=%s AND status='COMPLETED' AND object_key IS NOT NULL
                  AND version<%s ORDER BY version DESC LIMIT 1
                """,
                (project["id"], active["version"]),
            ).fetchone()
            if target is None:
                return None
            connection.execute(
                "UPDATE podcast_projects SET current_version=%s,updated_at=now() WHERE id=%s",
                (target["version"], project["id"]),
            )
            revoked = connection.execute(
                """
                UPDATE podcast_shares share SET revoked_at=COALESCE(revoked_at,now())
                FROM podcast_versions version
                WHERE share.podcast_version_id=version.id AND version.project_id=%s
                  AND version.id<>%s AND share.revoked_at IS NULL RETURNING share.id
                """,
                (project["id"], target["id"]),
            ).fetchall()
            return {
                "recording_id": recording_id,
                "from_version": active["version"],
                "to_version": target["version"],
                "podcast_version_id": target["id"],
                "revoked_share_count": len(revoked),
            }

    def revoke_all_shares(self, user_id: UUID) -> int:
        with self._connect() as connection:
            rows = connection.execute(
                """
                UPDATE podcast_shares share SET revoked_at=COALESCE(revoked_at,now())
                FROM families family WHERE family.id=share.family_id
                  AND family.owner_user_id=%s AND share.revoked_at IS NULL
                RETURNING share.id
                """,
                (user_id,),
            ).fetchall()
            return len(rows)

"""Run a destructive lifecycle check against isolated, synthetic records only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from app.config import get_settings
from app.lifecycle_repository import PostgresLifecycleRepository
from app.upload_storage import LocalObjectStorage


settings = get_settings()
database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
storage = LocalObjectStorage(settings)
repository = PostgresLifecycleRepository(settings.database_url, storage)

user_id, family_id, recording_id, moment_id, creation_id = [uuid4() for _ in range(5)]
source_key = f"families/{family_id}/recordings/{recording_id}/source"
creation_key = f"families/{family_id}/recordings/{recording_id}/podcasts/{creation_id}.mp3"


def cleanup() -> None:
    storage.delete(source_key)
    storage.delete(creation_key)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM deletion_audits WHERE family_id=%s", (family_id,)
        )
        connection.execute("DELETE FROM families WHERE id=%s", (family_id,))
        connection.execute("DELETE FROM users WHERE id=%s", (user_id,))


try:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO users (id,status) VALUES (%s,'ACTIVE')", (user_id,)
        )
        connection.execute(
            "INSERT INTO families (id,owner_user_id,name) VALUES (%s,%s,%s)",
            (family_id, user_id, "阶段十隔离验证家庭"),
        )
        connection.execute(
            "INSERT INTO family_privacy_settings (family_id) VALUES (%s)", (family_id,)
        )
        connection.execute(
            """
            INSERT INTO recordings (
              id,family_id,created_by_user_id,title,original_file_name,
              object_key,status,delete_at
            ) VALUES (%s,%s,%s,%s,%s,%s,'READY_FOR_SELECTION',%s)
            """,
            (
                recording_id, family_id, user_id, "隔离验证录音", "validation.wav",
                source_key,
                datetime.now(UTC) + timedelta(days=7),
            ),
        )
        connection.execute(
            """
            INSERT INTO moments (
              id,family_id,recording_id,title,score,storyboard,pipeline_version,
              selection_state,start_ms,end_ms
            ) VALUES (%s,%s,%s,%s,0.9,'{}','validation-v1','kept',0,1000)
            """,
            (moment_id, family_id, recording_id, "隔离验证高光"),
        )
        connection.execute(
            """
            INSERT INTO creations (
              id,family_id,moment_id,type,status,object_key,pipeline_version,title
            ) VALUES (%s,%s,%s,'PODCAST','COMPLETED',%s,'validation-v1',%s)
            """,
            (creation_id, family_id, moment_id, creation_key, "隔离验证播客"),
        )

    source_path = storage.path_for(source_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"synthetic source")
    creation_path = storage.path_for(creation_key)
    creation_path.parent.mkdir(parents=True, exist_ok=True)
    creation_path.write_bytes(b"synthetic derived audio")

    share = repository.create_share(user_id, creation_id, 1)
    assert share is not None and share["id"] != share["creation_id"]
    assert repository.resolve_share(share["token"]) is not None
    assert repository.revoke_share(user_id, share["id"])["revoked_at"] is not None
    assert repository.resolve_share(share["token"]) is None

    deleted = repository.delete_recording(user_id, recording_id)
    assert deleted is not None and deleted["object_count"] == 2
    assert not source_path.exists() and not creation_path.exists()

    with psycopg.connect(database_url) as connection:
        remaining = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM recordings WHERE id=%s) +
              (SELECT count(*) FROM moments WHERE id=%s) +
              (SELECT count(*) FROM creations WHERE id=%s) +
              (SELECT count(*) FROM creation_shares WHERE creation_id=%s)
            """,
            (recording_id, moment_id, creation_id, creation_id),
        ).fetchone()[0]
        audits = connection.execute(
            """
            SELECT count(*) FROM deletion_audits
            WHERE family_id=%s AND target_id=%s AND result='COMPLETED'
            """,
            (family_id, recording_id),
        ).fetchone()[0]
    assert remaining == 0 and audits == 1
    print({
        "share_create_open_revoke": True,
        "database_cascade": True,
        "object_cleanup": True,
        "deletion_audit": True,
    })
finally:
    cleanup()

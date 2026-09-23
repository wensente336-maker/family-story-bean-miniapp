"""Opt-in real PostgreSQL tests. All records live in a unique disposable schema.

Run: PODCAST_TRASH_DB_TEST=1 .venv/bin/python -m pytest tests/test_podcast_trash_integration.py
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.config import get_settings
from app.main import app
from app.podcast_product_repository import PostgresPodcastProductRepository
from app.podcast_product_router import get_podcast_product_repository
from app.podcast_share_repository import PostgresPodcastShareRepository
from app.podcast_share_router import get_podcast_share_repository
from app.podcast_render_repository import PostgresPodcastRenderRepository

pytestmark = pytest.mark.skipif(os.getenv("PODCAST_TRASH_DB_TEST") != "1", reason="requires opt-in local PostgreSQL")


@pytest.fixture()
def database():
    dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    schema = "podcast_trash_test_" + uuid4().hex
    admin = psycopg.connect(dsn, autocommit=True)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        admin.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        for migration in sorted((Path(__file__).resolve().parents[1] / "database/migrations").glob("*.sql")):
            if not migration.name.endswith(".down.sql"):
                admin.execute(migration.read_text())
        def connect():
            connection = psycopg.connect(dsn, row_factory=dict_row)
            connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
            return connection
        products = PostgresPodcastProductRepository(dsn)
        shares = PostgresPodcastShareRepository(dsn)
        renders = PostgresPodcastRenderRepository(dsn)
        for repo in (products, shares, renders):
            repo._connect = connect
        owner, stranger, family, recording, project = [uuid4() for _ in range(5)]
        versions = [uuid4(), uuid4()]
        job = uuid4()
        with connect() as db:
            db.execute("INSERT INTO users(id) VALUES (%s),(%s)", (owner, stranger))
            db.execute("INSERT INTO families(id,owner_user_id,name) VALUES (%s,%s,'测试家庭')", (family, owner))
            db.execute("INSERT INTO recordings(id,family_id,created_by_user_id,title,original_file_name) VALUES (%s,%s,%s,'回收站测试录音','test.wav')", (recording, family, owner))
            db.execute("INSERT INTO podcast_projects(id,family_id,recording_id,created_by_user_id,current_version) VALUES (%s,%s,%s,%s,2)", (project, family, recording, owner))
            for number, version in enumerate(versions, 1):
                material = uuid4()
                db.execute("""INSERT INTO podcast_versions(id,family_id,project_id,version,status,title,object_key,render_fingerprint)
                    VALUES (%s,%s,%s,%s,'COMPLETED','回收站测试作品',%s,'preserved-fingerprint')""",
                    (version, family, project, number, f"families/{family}/recordings/{recording}/podcasts/{version}/v{number}.mp3"))
                db.execute("""INSERT INTO podcast_material_sets(id,family_id,podcast_version_id,recording_id,status)
                    VALUES (%s,%s,%s,%s,'CONFIRMED')""", (material, family, version, recording))
                db.execute("""INSERT INTO podcast_plans(family_id,podcast_version_id,material_set_id,status,plan)
                    VALUES (%s,%s,%s,'CONFIRMED','{"external_share_allowed":true}')""", (family, version, material))
            db.execute("""INSERT INTO podcast_render_jobs(id,family_id,podcast_version_id,idempotency_key,status)
                VALUES (%s,%s,%s,%s,'COMPLETED')""", (job, family, versions[1], uuid4().hex))
            db.execute("""INSERT INTO podcast_cover_assets(family_id,podcast_version_id,object_key,media_type,width,height,byte_size,sha256)
                VALUES (%s,%s,'cover.webp','image/webp',320,320,100,%s)""", (family, versions[1], "a" * 64))
        yield products, shares, renders, owner, stranger, recording, job, connect
    finally:
        # Only this fixture's freshly allocated schema is removed; application data is untouched.
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def test_project_trash_restore_preserves_all_versions_and_revokes_shares(database):
    products, shares, renders, owner, stranger, recording, job, connect = database
    products.update(owner, recording, "家庭测试", "简介保留", ["家庭日常", "恢复测试"])
    before = products.get_by_recording(owner, recording)
    shared = shares.create(owner, recording, 24)
    assert shares.resolve(shared["token"])
    assert products.set_deleted(stranger, recording, True) is None
    assert products.list_trash(stranger) == []
    assert products.set_deleted(owner, recording, True)["deleted_at"]
    assert products.set_deleted(owner, recording, True)["deleted_at"]
    assert products.list_by_tag(owner) == []
    assert products.list_by_tag(owner, "家庭日常") == []
    assert products.get_by_recording(owner, recording) is None
    assert products.update(owner, recording, "禁止编辑", "", []) is None
    assert products.save_cover(owner, recording, {}) is None
    assert products.delete_cover(owner, recording) is None
    assert renders.get_for_user(owner, job) is None
    assert shares.create(owner, recording, 24) is None
    assert shares.resolve(shared["token"]) is None
    assert len(products.list_trash(owner)) == 1
    assert products.set_deleted(stranger, recording, False) is None
    assert products.set_deleted(owner, recording, False)["deleted_at"] is None
    assert products.set_deleted(owner, recording, False)["deleted_at"] is None
    after = products.get_by_recording(owner, recording)
    assert after == before  # Includes asset identity, cover, tags, sources and original sort time.
    assert products.list_trash(owner) == []
    assert shares.resolve(shared["token"]) is None
    assert shares.resolve(shares.create(owner, recording, 24)["token"])
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM podcast_versions").fetchone()["n"] == 2
        assert db.execute("SELECT count(*) AS n FROM deletion_audits").fetchone()["n"] == 2


def test_delete_requires_confirmation_and_hides_cross_family_records(database):
    products, shares, _renders, owner, stranger, recording, _job, _connect = database
    app.dependency_overrides[current_user_id] = lambda: owner
    app.dependency_overrides[get_podcast_product_repository] = lambda: products
    app.dependency_overrides[get_podcast_share_repository] = lambda: shares
    try:
        with TestClient(app) as client:
            url = f"/v1/recordings/{recording}/podcast-product"
            assert client.delete(url).status_code == 422
            assert client.request("DELETE", url, json={"confirmed": False}).status_code == 422
            assert client.get(url).status_code == 200
            assert client.request("DELETE", url, json={"confirmed": True}).status_code == 200
            assert client.get(url).status_code == 404
            assert len(client.get("/v1/podcast-products/trash").json()["data"]) == 1
            app.dependency_overrides[current_user_id] = lambda: stranger
            assert client.get("/v1/podcast-products/trash").json()["data"] == []
            assert client.post(url + "/restore").status_code == 404
            app.dependency_overrides[current_user_id] = lambda: owner
            assert client.post(url + "/restore").status_code == 200
            assert client.get(url).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_concurrent_share_creation_and_deletion_do_not_reactivate_links(database):
    products, shares, _renders, owner, _stranger, recording, _job, _connect = database
    with ThreadPoolExecutor(max_workers=2) as pool:
        for _ in range(10):
            products.set_deleted(owner, recording, False)
            sharing = pool.submit(shares.create, owner, recording, 24)
            deleting = pool.submit(products.set_deleted, owner, recording, True)
            share = sharing.result(timeout=10)
            deleting.result(timeout=10)
            products.set_deleted(owner, recording, False)
            if share:
                assert shares.resolve(share["token"]) is None


def test_failed_delete_rolls_back_visibility_and_share_revocation(database):
    products, shares, _renders, owner, _stranger, recording, _job, connect = database
    shared = shares.create(owner, recording, 24)
    with connect() as db:
        db.execute("ALTER TABLE deletion_audits ADD CONSTRAINT test_audit_failure CHECK (scope <> 'podcast_trash')")
    with pytest.raises(psycopg.errors.CheckViolation):
        products.set_deleted(owner, recording, True)
    assert products.get_by_recording(owner, recording) is not None
    assert products.list_trash(owner) == []
    assert shares.resolve(shared["token"]) is not None

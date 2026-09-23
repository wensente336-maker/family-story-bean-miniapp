from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.config import Settings
from app.main import app
from app.podcast_release import PodcastReleasePolicy
from app.podcast_release_router import get_podcast_release_repository
from app import podcast_render_router, podcast_share_router


class MemoryReleaseRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.recording_id = uuid4()
        self.version_id = uuid4()
        self.revoked = 0
        self.rolled_back = False

    def metrics(self, user_id):
        if user_id != self.user_id:
            return None
        return {
            "generation_total": 30, "generation_completed": 30,
            "generation_failed": 0, "first_pass_success_rate": 0.9333,
            "usable_product_rate": 1.0, "degradation_rate": 0.0667,
            "generation_p95_seconds": 82.4, "failure_reasons": {},
            "active_shares": 2, "share_accesses": 18,
        }

    def rollback(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id or self.rolled_back:
            return None
        self.rolled_back = True
        return {
            "recording_id": recording_id, "from_version": 3, "to_version": 2,
            "podcast_version_id": self.version_id, "revoked_share_count": 2,
        }

    def revoke_all_shares(self, user_id):
        if user_id != self.user_id:
            return 0
        self.revoked += 3
        return 3


def test_release_policy_supports_open_allowlist_and_emergency_off():
    user_id = uuid4()
    assert PodcastReleasePolicy(Settings(podcast_rollout_mode="open")).can_create(user_id)
    assert not PodcastReleasePolicy(Settings(podcast_rollout_mode="off")).can_create(user_id)
    allowed = Settings(
        podcast_rollout_mode="allowlist", podcast_rollout_user_ids=str(user_id)
    )
    assert PodcastReleasePolicy(allowed).can_create(user_id)
    assert not PodcastReleasePolicy(allowed).can_share(uuid4())
    assert not PodcastReleasePolicy(Settings(
        podcast_rollout_mode="open", podcast_sharing_enabled=False
    )).can_share(user_id)


def test_metrics_rollback_and_test_share_cleanup_are_owner_scoped():
    user_id = uuid4()
    repository = MemoryReleaseRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_release_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            metrics = client.get("/v1/ops/podcast-metrics")
            assert metrics.status_code == 200
            assert metrics.json()["data"]["generation_total"] == 30
            assert metrics.json()["data"]["usable_product_rate"] == 1.0

            invalid = client.post(
                f"/v1/ops/recordings/{repository.recording_id}/rollback",
                json={"confirmation": "wrong"},
            )
            assert invalid.status_code == 422
            rollback = client.post(
                f"/v1/ops/recordings/{repository.recording_id}/rollback",
                json={"confirmation": "ROLLBACK_TO_PREVIOUS_COMPLETED"},
            )
            assert rollback.status_code == 200
            assert rollback.json()["data"]["to_version"] == 2
            assert rollback.json()["data"]["revoked_share_count"] == 2
            assert client.post(
                f"/v1/ops/recordings/{repository.recording_id}/rollback",
                json={"confirmation": "ROLLBACK_TO_PREVIOUS_COMPLETED"},
            ).status_code == 409

            cleanup = client.post(
                "/v1/ops/podcast-shares/revoke-all-test",
                json={"confirmation": "REVOKE_ALL_TEST_SHARES"},
            )
            assert cleanup.status_code == 200
            assert cleanup.json()["data"]["revoked_share_count"] == 3
    finally:
        app.dependency_overrides.clear()


def test_release_metrics_contract_has_no_family_or_asset_identifiers():
    user_id = uuid4()
    repository = MemoryReleaseRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_release_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            data = client.get("/v1/ops/podcast-metrics").json()["data"]
            serialized = str(data)
            assert "family_id" not in serialized
            assert "object_key" not in serialized
            assert "transcript" not in serialized
            assert "access_token" not in serialized
    finally:
        app.dependency_overrides.clear()


class MustNotRunRepository:
    def create_job(self, *_args):
        raise AssertionError("disabled creation reached repository")

    def create(self, *_args):
        raise AssertionError("disabled sharing reached repository")


def test_emergency_flags_block_new_render_and_share_before_writes(monkeypatch):
    user_id = uuid4()
    repository = MustNotRunRepository()
    settings = Settings(
        podcast_creation_enabled=False, podcast_sharing_enabled=False,
        podcast_rollout_mode="off",
    )
    monkeypatch.setattr(podcast_render_router, "get_settings", lambda: settings)
    monkeypatch.setattr(podcast_share_router, "get_settings", lambda: settings)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[podcast_render_router.get_podcast_render_repository] = lambda: repository
    app.dependency_overrides[podcast_render_router.get_podcast_render_service] = lambda: object()
    app.dependency_overrides[podcast_share_router.get_podcast_share_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            recording_id = uuid4()
            render = client.post(f"/v1/recordings/{recording_id}/podcast-render-jobs")
            share = client.post(
                f"/v1/recordings/{recording_id}/podcast-shares",
                json={"expires_in_hours": 24},
            )
            assert render.status_code == 503
            assert render.json()["error"]["code"] == "PODCAST_CREATION_PAUSED"
            assert share.status_code == 503
            assert share.json()["error"]["code"] == "PODCAST_SHARING_PAUSED"
    finally:
        app.dependency_overrides.clear()

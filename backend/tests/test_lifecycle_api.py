from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.lifecycle_router import get_lifecycle_repository
from app.lifecycle_repository import _token_hash
from app.main import app


class MemoryLifecycleRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.family_id = uuid4()
        self.recording_id = uuid4()
        self.creation_id = uuid4()
        self.share_id = uuid4()
        self.token = "public-share-token"
        self.revoked = False
        self.settings = {
            "family_id": self.family_id, "recording_retention_days": 7,
            "share_default_hours": 24, "sharing_enabled": True,
            "updated_at": datetime.now(UTC),
        }

    def timeline(self, user_id, content_type, member_id, date_from, date_to, limit):
        if user_id != self.user_id:
            return []
        rows = [{
            "id": self.creation_id, "kind": "podcast", "title": "家里的小剧场",
            "subtitle": "家庭播客", "status": "COMPLETED",
            "created_at": datetime.now(UTC), "recording_id": self.recording_id,
            "target_path": f"/podcasts/{self.creation_id}", "member_ids": [],
        }]
        return [row for row in rows if not content_type or row["kind"] == content_type][:limit]

    def create_share(self, user_id, creation_id, hours):
        if user_id != self.user_id or creation_id != self.creation_id or not self.settings["sharing_enabled"]:
            return None
        now = datetime.now(UTC)
        return {
            "id": self.share_id, "creation_id": self.creation_id,
            "creation_type": "PODCAST", "title": "家里的小剧场",
            "token": self.token, "expires_at": now + timedelta(hours=hours),
            "revoked_at": None, "access_count": 0, "created_at": now,
        }

    def list_shares(self, user_id):
        return [] if user_id != self.user_id else [self.create_share(user_id, self.creation_id, 24)]

    def revoke_share(self, user_id, share_id):
        if user_id != self.user_id or share_id != self.share_id:
            return None
        self.revoked = True
        row = self.create_share(user_id, self.creation_id, 24)
        row["revoked_at"] = datetime.now(UTC)
        return row

    def resolve_share(self, token, count_access=True):
        if token != self.token or self.revoked:
            return None
        return {
            "creation_id": self.creation_id, "creation_type": "PODCAST",
            "title": "家里的小剧场", "expires_at": datetime.now(UTC) + timedelta(hours=24),
            "object_key": "podcast.mp3", "panels": [],
        }

    def get_privacy_settings(self, user_id):
        return self.settings if user_id == self.user_id else None

    def update_privacy_settings(self, user_id, retention_days, share_hours, sharing_enabled):
        if user_id != self.user_id:
            return None
        self.settings.update({
            "recording_retention_days": retention_days, "share_default_hours": share_hours,
            "sharing_enabled": sharing_enabled, "updated_at": datetime.now(UTC),
        })
        return self.settings

    def delete_creation(self, user_id, creation_id):
        if user_id != self.user_id or creation_id != self.creation_id:
            return None
        return {
            "target_id": creation_id, "scope": "CREATION", "deleted": True,
            "object_count": 1, "completed_at": datetime.now(UTC),
        }

    def delete_recording(self, *_args):
        return None

    def delete_family(self, *_args):
        return None

    def metrics(self, user_id):
        if user_id != self.user_id:
            return None
        return {
            "recordings_total": 1, "upload_success_rate": 1.0,
            "analysis_success_rate": 1.0, "generation_success_rate": 1.0,
            "processing_p95_seconds": 42.5, "deletion_success_rate": 1.0,
            "active_shares": 1,
        }


@pytest.fixture()
def lifecycle_client():
    user_id = uuid4()
    repository = MemoryLifecycleRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_lifecycle_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_timeline_returns_real_navigation_target(lifecycle_client):
    client, repository = lifecycle_client
    response = client.get("/v1/timeline?content_type=podcast")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["target_path"] == f"/podcasts/{repository.creation_id}"


def test_share_can_be_created_opened_and_revoked(lifecycle_client):
    client, repository = lifecycle_client
    created = client.post(
        f"/v1/creations/{repository.creation_id}/shares", json={"expires_in_hours": 12}
    )
    assert created.status_code == 200
    assert created.json()["data"]["id"] == str(repository.share_id)
    assert created.json()["data"]["creation_id"] == str(repository.creation_id)
    assert created.json()["data"]["url"].endswith(f"/share/{repository.token}")
    assert client.get(f"/v1/public/shares/{repository.token}").status_code == 200

    revoked = client.delete(f"/v1/shares/{repository.share_id}")
    assert revoked.status_code == 200
    expired = client.get(f"/v1/public/shares/{repository.token}")
    assert expired.status_code == 404


def test_privacy_defaults_are_editable_and_sharing_can_be_disabled(lifecycle_client):
    client, repository = lifecycle_client
    response = client.put("/v1/privacy", json={
        "recording_retention_days": 14, "share_default_hours": 6, "sharing_enabled": False,
    })
    assert response.status_code == 200
    assert response.json()["data"]["recording_retention_days"] == 14
    assert client.post(
        f"/v1/creations/{repository.creation_id}/shares", json={"expires_in_hours": 6}
    ).status_code == 404


def test_cross_family_delete_is_not_disclosed(lifecycle_client):
    client, _repository = lifecycle_client
    response = client.delete(f"/v1/privacy/creations/{uuid4()}")
    assert response.status_code == 404


def test_cross_family_access_is_rejected_for_one_hundred_foreign_ids(lifecycle_client):
    client, _repository = lifecycle_client
    statuses = [
        client.delete(f"/v1/privacy/creations/{uuid4()}").status_code
        for _ in range(100)
    ]
    assert statuses == [404] * 100


def test_public_share_token_is_represented_by_one_way_digest():
    token = "a-private-share-token"
    digest = _token_hash(token)
    assert token not in digest
    assert len(digest) == 64
    assert digest == _token_hash(token)


def test_family_metrics_are_owner_scoped(lifecycle_client):
    client, _repository = lifecycle_client
    metrics = client.get("/v1/ops/family-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data"]["processing_p95_seconds"] == 42.5

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import time
from urllib.parse import urlparse
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.config import Settings
from app.main import app
from app.podcast_share_repository import PodcastShareNotAllowed, token_hash
from app.podcast_share_router import get_podcast_share_repository, get_share_storage
from app.recording_router import get_object_storage
from app.upload_storage import LocalObjectStorage


class MemoryPodcastShareRepository:
    def __init__(self, user_id, recording_id):
        self.user_id = user_id
        self.recording_id = recording_id
        self.version_id = uuid4()
        self.share_id = uuid4()
        self.token = "private-share-token"
        self.revoked = False
        self.expired = False
        self.access_count = 0
        self.created = False
        self.share_allowed = True
        self.audio_key = f"recordings/{recording_id}/podcasts/final.mp3"
        self.cover_key = f"recordings/{recording_id}/podcast-covers/final.webp"

    def row(self):
        now = datetime.now(UTC)
        return {
            "id": self.share_id, "podcast_version_id": self.version_id,
            "recording_id": self.recording_id, "family_id": uuid4(),
            "title": "会飞的西红柿", "description": "一段来自家里的笑声。",
            "object_key": self.audio_key, "cover_object_key": self.cover_key,
            "render_metadata": {"duration_ms": 123000, "render_mode": "narrated"},
            "tags": ["家庭日常", "欢乐瞬间"], "token": self.token,
            "expires_at": now - timedelta(minutes=1) if self.expired else now + timedelta(hours=24),
            "revoked_at": now if self.revoked else None, "access_count": self.access_count,
            "created_at": now - timedelta(minutes=5),
        }

    def create(self, user_id, recording_id, hours):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        if not self.share_allowed:
            raise PodcastShareNotAllowed("family-only material")
        self.created = True
        row = self.row(); row["expires_at"] = datetime.now(UTC) + timedelta(hours=hours)
        return row

    def list_for_user(self, user_id, recording_id=None):
        if user_id != self.user_id or not self.created:
            return []
        return [self.row()]

    def revoke(self, user_id, share_id):
        if user_id != self.user_id or share_id != self.share_id:
            return None
        self.revoked = True
        return self.row()

    def resolve(self, token, count_access=True):
        if token != self.token or self.revoked or self.expired or not self.share_allowed:
            return None
        if count_access:
            self.access_count += 1
        return deepcopy(self.row())


def test_share_token_is_one_way_hash():
    assert token_hash("secret") != "secret"
    assert len(token_hash("secret")) == 64
    assert token_hash("secret") == token_hash("secret")


def test_create_public_resolve_card_and_revoke_are_privacy_safe(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryPodcastShareRepository(user_id, recording_id)
    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    audio = storage.path_for(repository.audio_key); audio.parent.mkdir(parents=True); audio.write_bytes(b"ID3-audio")
    cover = storage.path_for(repository.cover_key); cover.parent.mkdir(parents=True); cover.write_bytes(b"RIFF-webp")
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_share_repository] = lambda: repository
    app.dependency_overrides[get_share_storage] = lambda: storage
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            created = client.post(
                f"/v1/recordings/{recording_id}/podcast-shares",
                json={"expires_in_hours": 24},
            )
            assert created.status_code == 200
            assert "/card" in created.json()["data"]["url"]
            assert client.post(
                f"/v1/recordings/{recording_id}/podcast-shares",
                json={"expires_in_hours": 169},
            ).status_code == 422

            public = client.get(f"/v1/public/podcast-shares/{repository.token}")
            assert public.status_code == 200
            data = public.json()["data"]
            serialized = str(data)
            assert "object_key" not in serialized
            assert "transcript" not in serialized
            assert "speaker" not in serialized
            assert set(data) == {
                "title", "description", "tags", "cover_url", "cover_download_url",
                "media_url", "expires_at", "duration_ms", "render_mode",
            }
            media_token = urlparse(data["media_url"]).path.rsplit("/", 1)[-1]
            claims = storage.verify_playback_token(media_token)
            assert 0 < claims.expires_at - int(time.time()) <= 600
            assert client.get(data["media_url"]).status_code == 200

            card = client.get(f"/v1/public/podcast-shares/{repository.token}/card")
            assert card.status_code == 200
            assert 'property="og:title"' in card.text
            assert repository.audio_key not in card.text
            assert "会飞的西红柿" in card.text
            assert repository.access_count == 2

            revoked = client.delete(f"/v1/podcast-shares/{repository.share_id}")
            assert revoked.status_code == 200
            assert client.get(data["media_url"]).status_code == 404
            assert client.get(data["cover_url"]).status_code == 404
            for _ in range(100):
                assert client.get(f"/v1/public/podcast-shares/{repository.token}").status_code == 404
            assert client.get(f"/v1/public/podcast-shares/{repository.token}/card").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_expired_share_cannot_issue_new_media_signature(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryPodcastShareRepository(user_id, recording_id)
    repository.expired = True
    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    app.dependency_overrides[get_podcast_share_repository] = lambda: repository
    app.dependency_overrides[get_share_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            response = client.get(f"/v1/public/podcast-shares/{repository.token}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "PODCAST_SHARE_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_family_only_material_cannot_create_external_share(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryPodcastShareRepository(user_id, recording_id)
    repository.share_allowed = False
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_share_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/v1/recordings/{recording_id}/podcast-shares",
                json={"expires_in_hours": 24},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "PODCAST_SHARE_NOT_ALLOWED"
            assert repository.created is False
    finally:
        app.dependency_overrides.clear()


def test_existing_share_stops_resolving_when_material_becomes_family_only(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryPodcastShareRepository(user_id, recording_id)
    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_share_repository] = lambda: repository
    app.dependency_overrides[get_share_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            created = client.post(
                f"/v1/recordings/{recording_id}/podcast-shares",
                json={"expires_in_hours": 24},
            )
            assert created.status_code == 200
            repository.share_allowed = False
            assert client.get(
                f"/v1/public/podcast-shares/{repository.token}"
            ).status_code == 404
            assert client.get(
                f"/v1/public/podcast-shares/{repository.token}/card"
            ).status_code == 404
    finally:
        app.dependency_overrides.clear()

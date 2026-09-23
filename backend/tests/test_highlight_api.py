from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.config import Settings
from app.highlight_router import get_highlight_repository, get_highlight_storage
from app.main import app
from app.upload_storage import LocalObjectStorage


class MemoryHighlightRepository:
    def __init__(self, user_id, recording_id):
        self.user_id = user_id
        self.work_id = uuid4()
        self.share_id = uuid4()
        self.token = "highlight-private-token"
        now = datetime.now(UTC)
        self.work = {
            "id": self.work_id, "source_moment_id": uuid4(),
            "recording_id": recording_id, "title": "奶奶的笑声",
            "quote": "那天大家都笑了。", "share_allowed": True,
            "start_ms": 1000, "end_ms": 6000, "duration_ms": 5000,
            "audio_status": "READY",
            "audio_object_key": f"recordings/{recording_id}/highlights/{self.work_id}/clip.mp3",
            "cover": None, "member_ids": [], "deleted_at": None,
            "created_at": now, "updated_at": now,
        }
        self.revoked = False
        self.liked = False
        self.comments = []

    def list_for_user(self, user_id, trashed=False):
        if user_id != self.user_id or bool(self.work["deleted_at"]) != trashed:
            return []
        return [deepcopy(self.work)]

    def get_for_user(self, user_id, work_id, trashed=False):
        if user_id != self.user_id or work_id != self.work_id or bool(self.work["deleted_at"]) != trashed:
            return None
        return deepcopy(self.work)

    def update(self, user_id, work_id, title, quote):
        if self.get_for_user(user_id, work_id) is None:
            return None
        self.work.update(title=title, quote=quote, updated_at=datetime.now(UTC))
        return deepcopy(self.work)

    def set_deleted(self, user_id, work_id, deleted):
        if user_id != self.user_id or work_id != self.work_id:
            return None
        self.work["deleted_at"] = datetime.now(UTC) if deleted else None
        if deleted:
            self.revoked = True
        return {"id": work_id, "deleted_at": self.work["deleted_at"]}

    def create_share(self, user_id, work_id, hours):
        if self.get_for_user(user_id, work_id) is None or not self.work["share_allowed"]:
            return None
        now = datetime.now(UTC)
        return {"id": self.share_id, "highlight_work_id": work_id,
                "title": self.work["title"], "token": self.token,
                "expires_at": now + timedelta(hours=hours), "revoked_at": None,
                "access_count": 0, "created_at": now}

    def list_shares(self, user_id, work_id):
        return []

    def revoke_share(self, user_id, share_id):
        return None

    def resolve_share(self, token, count_access=True):
        if token != self.token or self.revoked or self.work["deleted_at"]:
            return None
        return {**deepcopy(self.work), "highlight_work_id": self.work_id,
                "expires_at": datetime.now(UTC) + timedelta(hours=24),
                "cover_object_key": None}

    def set_like(self, user_id, work_id, liked):
        if user_id != self.user_id or work_id != self.work_id or self.work["deleted_at"]:
            return None
        self.liked = liked
        return {"highlight_work_id": work_id, "liked": liked, "like_count": int(liked)}

    def list_comments(self, user_id, work_id, cursor, limit):
        if user_id != self.user_id or work_id != self.work_id or self.work["deleted_at"]:
            return None
        return {"items": deepcopy(self.comments[:limit]), "next_cursor": None}

    def create_comment(self, user_id, work_id, body):
        if user_id != self.user_id or work_id != self.work_id or self.work["deleted_at"]:
            return None
        now = datetime.now(UTC)
        comment = {"id": uuid4(), "highlight_work_id": work_id, "author_name": "妈妈",
                   "body": body, "can_edit": True, "can_delete": True,
                   "created_at": now, "updated_at": now}
        self.comments.insert(0, comment)
        return deepcopy(comment)

    def update_comment(self, user_id, comment_id, body):
        for comment in self.comments:
            if user_id == self.user_id and comment["id"] == comment_id:
                comment["body"] = body; comment["updated_at"] = datetime.now(UTC)
                return deepcopy(comment)
        return None

    def delete_comment(self, user_id, comment_id):
        for index, comment in enumerate(self.comments):
            if user_id == self.user_id and comment["id"] == comment_id:
                self.comments.pop(index)
                return {"id": comment_id, "highlight_work_id": self.work_id}
        return None


def test_highlight_is_an_independent_editable_shareable_trashable_work(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryHighlightRepository(user_id, recording_id)
    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    audio = storage.path_for(repository.work["audio_object_key"])
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"ID3-highlight")
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_highlight_repository] = lambda: repository
    app.dependency_overrides[get_highlight_storage] = lambda: storage
    try:
        with TestClient(app) as client:
            listed = client.get("/v1/highlight-works")
            assert listed.status_code == 200
            assert listed.json()["data"][0]["audio_url"]

            edited = client.patch(
                f"/v1/highlight-works/{repository.work_id}",
                json={"title": "厨房里的笑声", "quote": "这一笑，值得一直留下。"},
            )
            assert edited.status_code == 200
            assert edited.json()["data"]["title"] == "厨房里的笑声"

            shared = client.post(
                f"/v1/highlight-works/{repository.work_id}/shares",
                json={"expires_in_hours": 24},
            )
            assert shared.status_code == 200
            assert f"/highlight-share/{repository.token}" in shared.json()["data"]["url"]
            public = client.get(f"/v1/public/highlight-shares/{repository.token}")
            assert public.status_code == 200
            assert client.get(public.json()["data"]["audio_url"]).content == b"ID3-highlight"

            removed = client.delete(f"/v1/highlight-works/{repository.work_id}")
            assert removed.status_code == 200
            assert client.get(f"/v1/public/highlight-shares/{repository.token}").status_code == 404
            assert client.get("/v1/highlight-works").json()["data"] == []
            assert len(client.get("/v1/highlight-works/trash").json()["data"]) == 1

            restored = client.post(f"/v1/highlight-works/{repository.work_id}/restore")
            assert restored.status_code == 200
            assert len(client.get("/v1/highlight-works").json()["data"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_highlight_share_respects_material_privacy(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryHighlightRepository(user_id, recording_id)
    repository.work["share_allowed"] = False
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_highlight_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/v1/highlight-works/{repository.work_id}/shares",
                json={"expires_in_hours": 24},
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_postcard_like_and_family_comments(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryHighlightRepository(user_id, recording_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_highlight_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            liked = client.post(f"/v1/highlight-works/{repository.work_id}/like")
            assert liked.status_code == 200
            assert liked.json()["data"] == {
                "highlight_work_id": str(repository.work_id), "liked": True, "like_count": 1,
            }
            assert client.delete(f"/v1/highlight-works/{repository.work_id}/like").json()["data"]["like_count"] == 0

            created = client.post(
                f"/v1/highlight-works/{repository.work_id}/comments",
                json={"body": "这一句我也一直记得。"},
            )
            assert created.status_code == 200
            comment_id = created.json()["data"]["id"]
            assert client.get(f"/v1/highlight-works/{repository.work_id}/comments").json()["data"]["items"][0]["author_name"] == "妈妈"
            edited = client.patch(f"/v1/highlight-comments/{comment_id}", json={"body": "这一刻我也一直记得。"})
            assert edited.status_code == 200
            assert edited.json()["data"]["body"] == "这一刻我也一直记得。"
            assert client.delete(f"/v1/highlight-comments/{comment_id}").status_code == 200
            assert client.get(f"/v1/highlight-works/{repository.work_id}/comments").json()["data"]["items"] == []
    finally:
        app.dependency_overrides.clear()

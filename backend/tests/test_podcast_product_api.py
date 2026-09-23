from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.auth_router import current_user_id
from app.config import Settings
from app.main import app
from app.podcast_cover import CoverValidationError, PodcastCoverProcessor
from app.podcast_product_router import (
    get_podcast_product_repository, get_product_storage,
)
from app.podcast_product_repository import PostgresPodcastProductRepository
from app.recording_router import get_object_storage
from app.upload_storage import LocalObjectStorage


def image_bytes(format_name="JPEG", size=(900, 600), exif=True):
    image = Image.new("RGB", size, (224, 116, 91))
    buffer = BytesIO()
    metadata = Image.Exif()
    if exif:
        metadata[271] = "private-camera"
        metadata[272] = "family-device"
    image.save(buffer, format_name, exif=metadata)
    return buffer.getvalue()


class MemoryProductRepository:
    def __init__(self, user_id, recording_id):
        self.user_id = user_id
        self.recording_id = recording_id
        self.version_id = uuid4()
        self.family_id = uuid4()
        self.cover = None
        self.audio_fingerprint = "locked-audio-fingerprint"
        self.version = 3
        self.title = "会飞的西红柿"
        self.description = "一次晚饭时的家庭笑声。"
        self.selected_tags = []
        self.liked = False
        self.comments = []
        self.available_tags = [
            {"id": uuid4(), "name": "家庭日常", "kind": "system"},
            {"id": uuid4(), "name": "欢乐瞬间", "kind": "system"},
        ]

    def payload(self):
        now = datetime.now(UTC)
        return {
            "podcast_version_id": self.version_id, "recording_id": self.recording_id,
            "version": self.version, "status": "COMPLETED", "title": self.title,
            "description": self.description, "duration_ms": 126000,
            "render_mode": "narrated", "audio_asset_fingerprint": self.audio_fingerprint,
            "cover": deepcopy(self.cover), "tags": deepcopy(self.selected_tags),
            "available_tags": deepcopy(self.available_tags),
            "chapters": [{"segment_index": 1, "kind": "original", "label": "家人笑声", "start_ms": 0, "end_ms": 1800, "source_segment_id": uuid4()}],
            "sources": [{"material_id": uuid4(), "source_segment_id": uuid4(), "speaker_label": "妈妈", "start_ms": 1000, "end_ms": 2600, "confirmed_text": "先把桌子擦干净。"}],
            "created_at": now, "updated_at": now,
            "like_count": 1 if self.liked else 0, "comment_count": len(self.comments),
            "liked_by_me": self.liked, "can_edit": True, "can_comment": True,
        }

    def get_by_recording(self, user_id, recording_id):
        return self.payload() if user_id == self.user_id and recording_id == self.recording_id else None

    def update(self, user_id, recording_id, title, description, tags):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        self.title, self.description = title, description
        known = {item["name"]: item for item in self.available_tags}
        self.selected_tags = []
        for name in tags:
            if name not in known:
                known[name] = {"id": uuid4(), "name": name, "kind": "custom"}
                self.available_tags.append(known[name])
            self.selected_tags.append(known[name])
        return self.payload()

    def save_cover(self, user_id, recording_id, cover):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        old = [] if self.cover is None else [self.cover["object_key"], self.cover["thumbnail_object_key"]]
        self.cover = {"id": uuid4(), **cover}
        return self.payload(), old

    def delete_cover(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        old = [] if self.cover is None else [self.cover["object_key"], self.cover["thumbnail_object_key"]]
        self.cover = None
        return old

    def list_by_tag(self, user_id, tag=None):
        if user_id != self.user_id:
            return []
        if tag and tag not in [item["name"] for item in self.selected_tags]:
            return []
        return [self.payload()]

    def set_like(self, user_id, version_id, liked):
        if user_id != self.user_id or version_id != self.version_id:
            return None
        self.liked = liked
        return {"podcast_version_id": version_id, "liked": liked, "like_count": 1 if liked else 0}

    def list_comments(self, user_id, version_id, cursor, limit):
        if user_id != self.user_id or version_id != self.version_id:
            return None
        return {"items": deepcopy(self.comments[:limit]), "next_cursor": None}

    def create_comment(self, user_id, version_id, body):
        if user_id != self.user_id or version_id != self.version_id:
            return None
        now = datetime.now(UTC)
        item = {"id": uuid4(), "podcast_version_id": version_id, "author_name": "豆豆",
                "body": body, "can_edit": True, "can_delete": True, "created_at": now, "updated_at": now}
        self.comments.insert(0, item)
        return deepcopy(item)

    def update_comment(self, user_id, comment_id, body):
        if user_id != self.user_id:
            return None
        for item in self.comments:
            if item["id"] == comment_id:
                item["body"] = body
                return deepcopy(item)
        return None

    def delete_comment(self, user_id, comment_id):
        if user_id != self.user_id:
            return None
        for index, item in enumerate(self.comments):
            if item["id"] == comment_id:
                self.comments.pop(index)
                return {"id": comment_id, "podcast_version_id": self.version_id}
        return None


@pytest.fixture()
def product_client(tmp_path):
    user_id, recording_id = uuid4(), uuid4()
    repository = MemoryProductRepository(user_id, recording_id)
    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_product_repository] = lambda: repository
    app.dependency_overrides[get_product_storage] = lambda: storage
    app.dependency_overrides[get_object_storage] = lambda: storage
    with TestClient(app) as client:
        yield client, repository, recording_id
    app.dependency_overrides.clear()


def test_cover_processor_strips_exif_and_generates_square_derivatives():
    result = PodcastCoverProcessor().process(image_bytes(), "image/jpeg", 0.2, 0.8)
    with Image.open(BytesIO(result.main)) as main:
        assert main.size == (1200, 1200)
        assert not main.getexif()
    with Image.open(BytesIO(result.thumbnail)) as thumbnail:
        assert thumbnail.size == (320, 320)
        assert not thumbnail.getexif()


@pytest.mark.parametrize(
    ("format_name", "media_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_cover_processor_accepts_supported_image_encodings(format_name, media_type):
    result = PodcastCoverProcessor().process(
        image_bytes(format_name, (720, 900), exif=format_name == "JPEG"), media_type
    )
    assert result.media_type == "image/webp"
    assert len(result.sha256) == 64


@pytest.mark.parametrize("media_type", ["image/gif", "application/pdf", "text/plain"])
def test_cover_processor_rejects_unsupported_formats(media_type):
    with pytest.raises(CoverValidationError):
        PodcastCoverProcessor().process(b"not-an-image", media_type)


def test_cover_processor_rejects_disguised_gif():
    gif = Image.new("RGB", (200, 200), (12, 55, 54))
    buffer = BytesIO(); gif.save(buffer, "GIF")
    with pytest.raises(CoverValidationError):
        PodcastCoverProcessor().process(buffer.getvalue(), "image/jpeg")


def test_product_metadata_and_tags_do_not_change_audio_identity(product_client):
    client, repository, recording_id = product_client
    before = client.get(f"/v1/recordings/{recording_id}/podcast-product").json()["data"]
    response = client.patch(f"/v1/recordings/{recording_id}/podcast-product", json={
        "title": "番茄事故小剧场", "description": "家里最好笑的两分钟。",
        "tags": ["家庭日常", "厨房趣事"],
    })
    assert response.status_code == 200
    after = response.json()["data"]
    assert after["audio_asset_fingerprint"] == before["audio_asset_fingerprint"]
    assert after["version"] == before["version"] == repository.version
    assert [item["name"] for item in after["tags"]] == ["家庭日常", "厨房趣事"]


def test_cover_replace_removes_old_derivatives_and_delete_restores_default(product_client):
    client, _, recording_id = product_client
    first = client.post(
        f"/v1/recordings/{recording_id}/podcast-product/cover",
        content=image_bytes(), headers={"Content-Type": "image/jpeg"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["cover"]["width"] == 1200
    assert first.json()["data"]["cover"]["height"] == 1600
    assert first.json()["data"]["cover"]["aspect_ratio"] == "3:4"
    first_url = first.json()["data"]["cover"]["url"]
    assert client.get(first_url).status_code == 200

    second = client.post(
        f"/v1/recordings/{recording_id}/podcast-product/cover?focal_x=0.1&focal_y=0.9",
        content=image_bytes("PNG", (640, 1000), exif=False), headers={"Content-Type": "image/png"},
    )
    assert second.status_code == 200
    assert second.json()["data"]["cover"]["sha256"]
    assert client.get(first_url).status_code == 404

    deleted = client.delete(f"/v1/recordings/{recording_id}/podcast-product/cover")
    assert deleted.status_code == 200
    product = client.get(f"/v1/recordings/{recording_id}/podcast-product").json()["data"]
    assert product["cover"] is None


def test_product_like_and_comment_flow(product_client):
    client, repository, _ = product_client
    version_id = repository.version_id
    liked = client.post(f"/v1/podcast-products/{version_id}/like")
    assert liked.status_code == 200
    assert liked.json()["data"]["liked"] is True
    created = client.post(f"/v1/podcast-products/{version_id}/comments", json={"body": "这段声音真好。"})
    assert created.status_code == 200
    comment_id = created.json()["data"]["id"]
    listed = client.get(f"/v1/podcast-products/{version_id}/comments")
    assert listed.json()["data"]["items"][0]["body"] == "这段声音真好。"
    assert client.patch(f"/v1/podcast-comments/{comment_id}", json={"body": "值得一直珍藏。"}).status_code == 200
    assert client.delete(f"/v1/podcast-comments/{comment_id}").status_code == 200
    assert client.delete(f"/v1/podcast-products/{version_id}/like").json()["data"]["liked"] is False


def test_product_rejects_more_than_five_or_duplicate_tags(product_client):
    client, _, recording_id = product_client
    base = f"/v1/recordings/{recording_id}/podcast-product"
    too_many = client.patch(base, json={"title": "标题", "description": "", "tags": list("123456")})
    duplicate = client.patch(base, json={"title": "标题", "description": "", "tags": ["日常", "日常"]})
    blank_title = client.patch(base, json={"title": "   ", "description": "", "tags": []})
    assert too_many.status_code == 422
    assert duplicate.status_code == 422
    assert blank_title.status_code == 422


def test_twenty_cross_family_product_reads_are_all_denied(product_client):
    client, _, _recording_id = product_client
    for _ in range(20):
        response = client.get(f"/v1/recordings/{uuid4()}/podcast-product")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PODCAST_PRODUCT_NOT_FOUND"


class EmptyListResult:
    def fetchall(self):
        return []


class ProductListConnection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.calls.append((" ".join(statement.split()), parameters))
        return EmptyListResult()


def test_unfiltered_product_list_never_binds_an_untyped_null():
    connection = ProductListConnection()
    repository = PostgresPodcastProductRepository("postgresql://unused")
    repository._connect = lambda: connection
    user_id = uuid4()

    assert repository.list_by_tag(user_id) == []
    assert connection.calls[0][1] == (user_id,)
    assert "%s IS NULL" not in connection.calls[0][0]

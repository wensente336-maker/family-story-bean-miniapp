from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.storybook_repository import PostgresStorybookRepository
from app.storybook_router import get_storybook_repository
from app.storybook_router import get_storybook_audio_renderer
from app.storybook_router import get_storybook_experience_renderer
from app.recording_router import get_object_storage


def make_storybook(comic_id):
    now = datetime.now(UTC)
    storybook_id = uuid4()
    recording_id = uuid4()
    segment_id = uuid4()
    pages = [
        {
            "index": 0,
            "type": "cover",
            "title": "会飞的西红柿",
            "narration": "这是一本家庭故事书。",
            "panel_index": 1,
            "panel_version": 1,
            "clip": None,
        },
        {
            "index": 1,
            "type": "story",
            "title": "一颗会飞的西红柿",
            "narration": "一个意外的小插曲突然发生。",
            "panel_index": 1,
            "panel_version": 1,
            "clip": {
                "source_segment_id": segment_id,
                "start_ms": 33000,
                "end_ms": 37500,
            },
        },
        {
            "index": 2,
            "type": "ending",
            "title": "家人的笑声，就是故事的封底",
            "narration": "这段快乐被留了下来。",
            "panel_index": 1,
            "panel_version": 1,
            "clip": None,
        },
    ]
    manifest = {
        "schema_version": "storybook-manifest-v1",
        "source_comic_id": comic_id,
        "source_comic_version": 1,
        "title": "会飞的西红柿",
        "page_count": len(pages),
        "audio": {
            "background_mode": "client-synthesized",
            "page_turn_mode": "client-synthesized",
            "narration_mode": "browser-speech",
            "highlight_source": "recording-source-segments",
        },
        "pages": pages,
    }
    return {
        "id": storybook_id,
        "comic_id": comic_id,
        "recording_id": recording_id,
        "title": "会飞的西红柿",
        "status": "DRAFT",
        "current_version": 1,
        "schema_version": "storybook-manifest-v1",
        "source_comic_version": 1,
        "manifest": manifest,
        "created_at": now,
        "updated_at": now,
    }


class MemoryStorybookRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.comic_id = uuid4()
        self.storybook = make_storybook(self.comic_id)
        self.create_calls = 0
        self.audio_assets = []
        self.storybook_version_id = uuid4()
        self.experience_track = None
        segment_id = self.storybook["manifest"]["pages"][1]["clip"]["source_segment_id"]
        now = datetime.now(UTC)
        self.story_plan = {
            "id": uuid4(),
            "storybook_id": self.storybook["id"],
            "storybook_version_id": self.storybook_version_id,
            "source_recording_id": self.storybook["recording_id"],
            "status": "CONFIRMED",
            "revision": 1,
            "source_schema_version": "sound-story-source-v1",
            "director_schema_version": "sound-story-director-v1",
            "source_story": {
                "schema_version": "sound-story-source-v1",
                "narration_style": "温暖克制",
                "clips": [{
                    "source_segment_id": str(segment_id),
                    "speaker_key": "speaker_1", "speaker_name": "苗苗",
                    "start_ms": 33000, "end_ms": 37500,
                    "text": "差点飞到奶奶家。", "included": True,
                    "locked": True, "role": "original",
                }],
            },
            "director_script": {
                "schema_version": "sound-story-director-v1", "title": "会飞的西红柿",
                "scenes": [],
            },
            "created_at": now, "updated_at": now,
        }

    def create_or_refresh(self, user_id, comic_id):
        if user_id != self.user_id or comic_id != self.comic_id:
            return None
        self.create_calls += 1
        return self.storybook

    def get_for_user(self, user_id, storybook_id):
        if user_id == self.user_id and storybook_id == self.storybook["id"]:
            return self.storybook
        return None

    def list_versions(self, user_id, storybook_id):
        if self.get_for_user(user_id, storybook_id) is None:
            return None
        return [{
            "version": 1,
            "schema_version": "storybook-manifest-v1",
            "source_comic_version": 1,
            "created_at": self.storybook["created_at"],
        }]

    def get_version(self, user_id, storybook_id, version):
        if self.get_for_user(user_id, storybook_id) is None or version != 1:
            return None
        return {
            "storybook_id": storybook_id,
            "version": 1,
            "schema_version": "storybook-manifest-v1",
            "source_comic_version": 1,
            "manifest": self.storybook["manifest"],
            "created_at": self.storybook["created_at"],
        }

    def get_audio_context(self, user_id, storybook_id):
        if self.get_for_user(user_id, storybook_id) is None:
            return None
        return {
            "storybook_id": storybook_id,
            "family_id": uuid4(),
            "current_version": 1,
            "storybook_version_id": self.storybook_version_id,
            "manifest": self.storybook["manifest"],
            "source_recording_id": self.storybook["recording_id"],
            "source_object_key": (
                f"families/family-1/recordings/{self.storybook['recording_id']}/source"
            ),
            "source_media_type": "audio/mpeg",
            "storyboard": {
                "scene": "家庭晚餐",
                "source_segments": [{
                    "transcript_segment_id": str(
                        self.storybook["manifest"]["pages"][1]["clip"]["source_segment_id"]
                    ),
                    "quote": "差点飞到奶奶家。",
                }],
            },
            "comic_metadata": {},
        }

    def get_story_source_context(self, user_id, storybook_id):
        context = self.get_audio_context(user_id, storybook_id)
        if context is None:
            return None
        clip = self.storybook["manifest"]["pages"][1]["clip"]
        return {
            **context,
            "title": self.storybook["title"],
            "transcript_segments": [{
                "id": clip["source_segment_id"], "speaker_key": "speaker_1",
                "speaker_name": "苗苗", "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"], "text": "差点飞到奶奶家。",
            }],
        }

    def list_audio_assets(self, _storybook_version_id):
        return self.audio_assets

    def save_audio_asset(self, asset):
        saved = {
            **asset,
            "id": uuid4(),
            "kind": "ORIGINAL_CLIP",
            "media_type": "audio/mpeg",
            "created_at": datetime.now(UTC),
        }
        self.audio_assets.append(saved)
        return saved

    def mark_audio_ready(self, _storybook_id):
        self.storybook["status"] = "READY"

    def get_experience_track(self, _storybook_version_id):
        return self.experience_track

    def save_experience_track(self, track):
        self.experience_track = {
            **track,
            "id": uuid4(),
            "status": "READY",
            "media_type": "audio/mpeg",
        }
        return self.experience_track

    def get_story_plan(self, _storybook_version_id):
        return self.story_plan

    def save_story_plan(self, plan):
        now = datetime.now(UTC)
        revision = self.story_plan["revision"] + 1 if self.story_plan else 1
        self.story_plan = {
            **plan, "id": self.story_plan["id"] if self.story_plan else uuid4(),
            "storybook_id": self.storybook["id"], "revision": revision,
            "created_at": self.story_plan["created_at"] if self.story_plan else now,
            "updated_at": now,
        }
        return self.story_plan

    def invalidate_experience_track(self, _storybook_version_id):
        if not self.experience_track:
            return None
        object_key = self.experience_track["object_key"]
        self.experience_track = None
        return object_key


class FakeStorage:
    def __init__(self, root):
        self.root = root

    def path_for(self, object_key):
        return self.root / object_key

    def issue_playback_token(self, recording_id, object_key, _media_type):
        return f"test-{recording_id}-{object_key.rsplit('/', 1)[-1]}", 2000000000

    def delete(self, object_key):
        self.path_for(object_key).unlink(missing_ok=True)


class FakeRenderer:
    def __init__(self, storage):
        self.storage = storage
        self.calls = 0

    def render_clip(self, _source_key, destination_key, start_ms, end_ms):
        self.calls += 1
        destination = self.storage.path_for(destination_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake mp3")
        return end_ms - start_ms


class FakeExperienceRenderer:
    def __init__(self, storage):
        self.storage = storage
        self.calls = 0

    def render(self, context, destination_key):
        self.calls += 1
        destination = self.storage.path_for(destination_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"continuous fake mp3")
        segment_id = context["manifest"]["pages"][1]["clip"]["source_segment_id"]
        scenes = [{
            "page_index": 0, "type": "cover", "title": "会飞的西红柿",
            "narration": "故事开始了。", "quote": None,
            "source_segment_id": None, "image_prompt": "封面",
            "audio_start_ms": 0, "audio_end_ms": 1800,
        }, {
            "page_index": 1, "type": "story", "title": "第一幕",
            "narration": "晚饭桌上发生了意外。", "quote": "差点飞到奶奶家。",
            "source_segment_id": segment_id, "image_prompt": "第一幕",
            "audio_start_ms": 1800, "audio_end_ms": 6300,
        }]
        cues = [{
            "segment_index": 1, "kind": "narration", "label": "故事解说",
            "text": "故事开始了。", "page_index": 0,
            "start_ms": 0, "end_ms": 1800, "source_segment_id": None,
        }, {
            "segment_index": 2, "kind": "original", "label": "家人真实原声",
            "text": "差点飞到奶奶家。", "page_index": 1,
            "start_ms": 1800, "end_ms": 6300, "source_segment_id": segment_id,
        }]
        return {
            "storyline": {"schema_version": "storybook-storyline-v1", "scenes": scenes},
            "cues": cues,
            "metadata": {
                "duration_ms": 6300, "tts_provider": "fake-natural-tts",
                "tts_voice": "warm-narrator", "music_source": "fake-ambient",
            },
        }


@pytest.fixture()
def storybook_client(tmp_path):
    user_id = uuid4()
    repository = MemoryStorybookRepository(user_id)
    storage = FakeStorage(tmp_path)
    renderer = FakeRenderer(storage)
    experience_renderer = FakeExperienceRenderer(storage)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_storybook_repository] = lambda: repository
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_storybook_audio_renderer] = lambda: renderer
    app.dependency_overrides[get_storybook_experience_renderer] = lambda: experience_renderer
    repository.experience_renderer = experience_renderer
    with TestClient(app) as client:
        yield client, repository, renderer
    app.dependency_overrides.clear()


def test_create_storybook_returns_versioned_manifest(storybook_client):
    client, repository, _renderer = storybook_client
    response = client.post(f"/v1/comics/{repository.comic_id}/storybook")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["current_version"] == 1
    assert data["manifest"]["schema_version"] == "storybook-manifest-v1"
    assert data["manifest"]["page_count"] == len(data["manifest"]["pages"])


def test_storybook_version_history_and_snapshot_are_readable(storybook_client):
    client, repository, _renderer = storybook_client
    storybook_id = repository.storybook["id"]
    versions = client.get(f"/v1/storybooks/{storybook_id}/versions")
    snapshot = client.get(f"/v1/storybooks/{storybook_id}/versions/1")
    assert versions.status_code == 200
    assert versions.json()["data"][0]["source_comic_version"] == 1
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["manifest"]["source_comic_id"] == str(repository.comic_id)


def test_other_family_cannot_read_storybook(storybook_client):
    client, _repository, _renderer = storybook_client
    response = client.get(f"/v1/storybooks/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORYBOOK_NOT_FOUND"


def test_audio_session_materializes_and_reuses_private_page_clip(storybook_client):
    client, repository, renderer = storybook_client
    storybook_id = repository.storybook["id"]

    first = client.post(f"/v1/storybooks/{storybook_id}/audio-session")
    second = client.post(f"/v1/storybooks/{storybook_id}/audio-session")

    assert first.status_code == 200
    assert second.status_code == 200
    clip = first.json()["data"]["clips"][0]
    assert clip["page_index"] == 1
    assert clip["original_start_ms"] == 33000
    assert clip["duration_ms"] == 4500
    assert clip["url"].startswith("http://testserver/v1/playback/test-")
    assert renderer.calls == 1
    assert repository.storybook["status"] == "READY"


def test_experience_session_returns_one_track_with_scene_cues(storybook_client):
    client, repository, _renderer = storybook_client
    storybook_id = repository.storybook["id"]

    first = client.post(f"/v1/storybooks/{storybook_id}/experience-session")
    second = client.post(f"/v1/storybooks/{storybook_id}/experience-session")

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()["data"]
    assert data["duration_ms"] == 6300
    assert data["scenes"][1]["audio_start_ms"] == 1800
    assert data["cues"][1]["kind"] == "original"
    assert data["narrator_provider"] == "fake-natural-tts"
    assert repository.experience_renderer.calls == 1


def test_story_plan_exposes_original_voice_and_director_scenes(storybook_client):
    client, repository, _renderer = storybook_client
    storybook_id = repository.storybook["id"]

    response = client.post(f"/v1/storybooks/{storybook_id}/story-plan/draft")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_story"]["clips"][0]["speaker_name"] == "苗苗"
    assert data["status"] == "CONFIRMED"


def test_story_plan_update_rebuilds_director_and_invalidates_audio(storybook_client):
    client, repository, _renderer = storybook_client
    storybook_id = repository.storybook["id"]
    segment_id = repository.story_plan["source_story"]["clips"][0]["source_segment_id"]

    response = client.patch(f"/v1/storybooks/{storybook_id}/story-plan", json={
        "clips": [{"source_segment_id": segment_id, "included": True}],
        "narration_style": "温暖克制",
        "status": "CONFIRMED",
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["revision"] == 2
    assert data["director_script"]["creative_rule"] == "sound-first"
    assert data["director_script"]["scenes"][0]["audio_sequence"][0]["kind"] == "narration"


def test_manifest_builder_keeps_panel_and_source_versions():
    comic_id = uuid4()
    source_segment_id = uuid4()
    comic = {"id": comic_id, "title": "家庭晚餐", "version": 7}
    panels = [{
        "panel_index": 1,
        "version": 3,
        "narration": "西红柿飞过了餐桌。",
        "dialogue": "差点飞到奶奶家。",
        "source_segment_id": source_segment_id,
        "clip_start_ms": 1200,
        "clip_end_ms": 4800,
    }]

    manifest = PostgresStorybookRepository.build_manifest(comic, panels)

    assert manifest["source_comic_version"] == 7
    assert manifest["pages"][1]["panel_version"] == 3
    assert manifest["pages"][1]["clip"] == {
        "source_segment_id": str(source_segment_id),
        "start_ms": 1200,
        "end_ms": 4800,
    }

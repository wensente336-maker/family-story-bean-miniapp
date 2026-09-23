from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.podcast_render_router import (
    get_podcast_render_repository,
    get_podcast_render_service,
)
from app.podcast_render_service import PodcastRenderService


class MemoryRenderRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.recording_id = uuid4()
        self.family_id = uuid4()
        self.version_id = uuid4()
        self.job_id = uuid4()
        self.confirmed = True
        self.job = None
        self.result = {"object_key": None, "render_metadata": {}}
        material_id = uuid4()
        self.context = {
            "family_id": self.family_id,
            "recording_id": self.recording_id,
            "podcast_version_id": self.version_id,
            "version": 1,
            "source_object_key": f"families/{self.family_id}/recordings/{self.recording_id}/source",
            "music_style": "warm-acoustic-light",
            "plan_revision": 3,
            "plan": {"segments": [
                {"segment_index": 1, "kind": "narration", "label": "开场", "text": "这是开场。", "source_material_ids": [str(material_id)]},
                {"segment_index": 2, "kind": "original", "label": "妈妈原声", "text": "擦干净桌子。", "source_material_ids": [str(material_id)]},
                {"segment_index": 3, "kind": "narration", "label": "收尾", "text": "故事留在声音里。", "source_material_ids": [str(material_id)]},
            ]},
            "materials": [{
                "id": material_id, "source_segment_id": uuid4(), "start_ms": 1000,
                "end_ms": 3000, "confirmed_text": "擦干净桌子。", "speaker_label": "妈妈",
                "position": 1,
            }],
        }

    def _payload(self):
        return {"job": deepcopy(self.job), "podcast_version_id": self.version_id, **deepcopy(self.result)}

    def create_job(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id or not self.confirmed:
            return None
        if self.job is None:
            now = datetime.now(UTC)
            self.job = {
                "id": self.job_id, "podcast_version_id": self.version_id,
                "status": "CREATED", "progress": 0, "retry_count": 0,
                "error_code": None, "error_detail": {}, "created_at": now, "updated_at": now,
            }
        return self._payload()

    def get_for_user(self, user_id, job_id):
        return self._payload() if user_id == self.user_id and self.job and job_id == self.job_id else None

    def get_by_recording(self, user_id, recording_id):
        return self._payload() if user_id == self.user_id and self.job and recording_id == self.recording_id else None

    def load_context(self, job_id):
        return deepcopy(self.context) if job_id == self.job_id else None

    def claim(self, job_id, token):
        if not self.job or self.job["status"] not in {"CREATED", "FAILED"}:
            return None
        self.job.update(status="GENERATING", progress=5, execution_token=token)
        return deepcopy(self.job)

    def update_progress(self, job_id, token, progress):
        self.job["progress"] = progress

    def complete(self, job_id, token, object_key, metadata):
        self.job.update(status="COMPLETED", progress=100)
        self.result = {"object_key": object_key, "render_metadata": metadata}
        return self._payload()

    def fail(self, job_id, token, code, detail):
        self.job.update(
            status="FAILED", retry_count=self.job["retry_count"] + 1,
            error_code=code, error_detail={"message": detail},
        )
        return self._payload()

    def reset_for_retry(self, user_id, job_id):
        if user_id != self.user_id or not self.job or self.job["status"] != "FAILED":
            return None
        self.job.update(status="CREATED", progress=0, error_code=None, error_detail={})
        return self._payload()


class FakeRenderer:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.last_segments = []

    def render(self, source, destination, segments, music_style):
        self.calls += 1
        self.last_segments = deepcopy(segments)
        if self.fail:
            raise RuntimeError("render unavailable")
        assert [item["kind"] for item in segments] == ["narration", "original", "narration"]
        return {
            "duration_ms": 12_000, "render_mode": "narrated",
            "tts_provider": "fake-natural", "tts_fallback_used": False,
            "music_style": music_style, "ducking_enabled": True, "timeline": [],
        }


@pytest.fixture()
def render_client():
    user_id = uuid4()
    repository = MemoryRenderRepository(user_id)
    renderer = FakeRenderer()
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_render_repository] = lambda: repository
    app.dependency_overrides[get_podcast_render_service] = lambda: PodcastRenderService(repository, renderer)
    with TestClient(app) as client:
        yield client, repository, renderer
    app.dependency_overrides.clear()


def test_requires_confirmed_plan(render_client):
    client, repository, _ = render_client
    repository.confirmed = False
    response = client.post(f"/v1/recordings/{repository.recording_id}/podcast-render-jobs")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PODCAST_PLAN_NOT_CONFIRMED"


def test_async_render_completes_and_duplicate_request_does_not_render_twice(render_client):
    client, repository, renderer = render_client
    path = f"/v1/recordings/{repository.recording_id}/podcast-render-jobs"
    created = client.post(path)
    assert created.status_code == 200
    completed = client.get(f"/v1/podcast-render-jobs/{repository.job_id}")
    assert completed.json()["data"]["job"]["status"] == "COMPLETED"
    assert completed.json()["data"]["render_metadata"]["ducking_enabled"] is True
    assert client.post(path).status_code == 200
    assert renderer.calls == 1


def test_failed_render_can_be_retried(render_client):
    client, repository, renderer = render_client
    renderer.fail = True
    client.post(f"/v1/recordings/{repository.recording_id}/podcast-render-jobs")
    assert repository.job["status"] == "FAILED"
    renderer.fail = False
    retried = client.post(f"/v1/podcast-render-jobs/{repository.job_id}/retry")
    assert retried.status_code == 200
    assert repository.job["status"] == "COMPLETED"
    assert repository.job["retry_count"] == 1


@pytest.mark.parametrize("sample_index", range(30))
def test_thirty_confirmed_material_boundaries_remain_exact(sample_index):
    user_id = uuid4()
    repository = MemoryRenderRepository(user_id)
    renderer = FakeRenderer()
    start_ms = 120 + sample_index * 431
    end_ms = start_ms + 850 + sample_index * 17
    repository.context["materials"][0].update(start_ms=start_ms, end_ms=end_ms)
    repository.create_job(user_id, repository.recording_id)

    result = PodcastRenderService(repository, renderer).run(repository.job_id)

    original = next(item for item in renderer.last_segments if item["kind"] == "original")
    assert result["job"]["status"] == "COMPLETED"
    assert (original["start_ms"], original["end_ms"]) == (start_ms, end_ms)

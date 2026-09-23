from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.podcast_plan_router import (
    get_narration_preview_service,
    get_podcast_narrative_generator,
    get_podcast_plan_repository,
)
from app.podcast_narrative import SafePodcastNarrativeGenerator


class MemoryPodcastPlanRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.recording_id = uuid4()
        self.version_id = uuid4()
        self.material_set_id = uuid4()
        self.family_id = uuid4()
        self.saved = None
        self.revision = 0
        self.context = {
            "recording_id": self.recording_id,
            "recording_title": "会飞的西红柿",
            "podcast_version_id": self.version_id,
            "material_set_id": self.material_set_id,
            "material_revision": 2,
            "family_id": self.family_id,
            "materials": [self._material(index) for index in range(1, 4)],
        }

    def _material(self, index):
        return {
            "id": uuid4(), "source_moment_id": uuid4(),
            "source_recording_id": self.recording_id,
            "source_segment_id": uuid4(), "family_member_id": uuid4(),
            "speaker_key": f"speaker_{index}",
            "speaker_label": ["苗苗", "妈妈", "爸爸"][index - 1],
            "role": ["setup", "highlight", "ending"][index - 1],
            "position": index, "start_ms": index * 1000,
            "end_ms": index * 1000 + 800,
            "original_text": f"原始文本 {index}",
            "confirmed_text": f"确认原声 {index}", "share_allowed": True,
        }

    def get_context(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        return deepcopy(self.context)

    def get_plan(self, user_id, recording_id):
        if self.get_context(user_id, recording_id) is None:
            return None
        return deepcopy(self.saved)

    def save_plan(self, user_id, recording_id, plan):
        context = self.get_context(user_id, recording_id)
        if context is None:
            return None
        if self.saved and self.saved["plan"]["narration_style"] == plan["narration_style"]:
            return deepcopy(self.saved)
        self.revision += 1
        self.saved = {
            **context,
            "plan": {
                **plan, "id": uuid4(), "material_set_id": self.material_set_id,
                "status": "DRAFT", "revision": self.revision,
                "schema_version": "podcast-plan-v1",
            },
        }
        return deepcopy(self.saved)

    def update_plan(self, user_id, recording_id, status, plan):
        if self.get_context(user_id, recording_id) is None or self.saved is None:
            return None
        if self.saved["plan"]["status"] == "CONFIRMED":
            return deepcopy(self.saved) if status == "CONFIRMED" else None
        self.revision += 1
        self.saved["plan"] = {
            **plan, "id": self.saved["plan"]["id"],
            "material_set_id": self.material_set_id, "status": status,
            "revision": self.revision, "schema_version": "podcast-plan-v1",
        }
        return deepcopy(self.saved)


class MemoryPreviewService:
    def create(self, recording_id, family_id, text, voice):
        return {
            "token": "signed-preview", "expires_at": 1_900_000_000,
            "provider": "preview-test", "voice": voice,
        }


@pytest.fixture()
def plan_client():
    user_id = uuid4()
    repository = MemoryPodcastPlanRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_plan_repository] = lambda: repository
    app.dependency_overrides[get_podcast_narrative_generator] = (
        lambda: SafePodcastNarrativeGenerator()
    )
    app.dependency_overrides[get_narration_preview_service] = lambda: MemoryPreviewService()
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_requires_confirmed_materials(plan_client):
    client, _ = plan_client
    response = client.post(
        f"/v1/recordings/{uuid4()}/podcast-plan/draft",
        json={"narration_style": "warm"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PODCAST_MATERIALS_NOT_CONFIRMED"


def test_creates_traceable_third_person_plan(plan_client):
    client, repository = plan_client
    response = client.post(
        f"/v1/recordings/{repository.recording_id}/podcast-plan/draft",
        json={"narration_style": "humorous"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["plan"]["narration_style"] == "humorous"
    assert data["plan"]["status"] == "DRAFT"
    assert all(data["plan"]["safety_checks"].values())
    originals = [item for item in data["plan"]["segments"] if item["kind"] == "original"]
    assert [item["text"] for item in originals] == [
        item["confirmed_text"] for item in data["materials"]
    ]


def test_gets_existing_plan_and_regeneration_increments_revision(plan_client):
    client, repository = plan_client
    path = f"/v1/recordings/{repository.recording_id}/podcast-plan/draft"
    assert client.post(path, json={"narration_style": "warm"}).status_code == 200
    second = client.post(path, json={"narration_style": "growth"})
    assert second.json()["data"]["plan"]["revision"] == 2
    fetched = client.get(f"/v1/recordings/{repository.recording_id}/podcast-plan")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["plan"]["narration_style"] == "growth"


def test_duplicate_generation_is_idempotent_for_same_materials_and_style(plan_client):
    client, repository = plan_client
    path = f"/v1/recordings/{repository.recording_id}/podcast-plan/draft"
    first = client.post(path, json={"narration_style": "warm"}).json()["data"]
    second = client.post(path, json={"narration_style": "warm"}).json()["data"]
    assert first["plan"]["id"] == second["plan"]["id"]
    assert second["plan"]["revision"] == 1


def editable_payload(plan, status="DRAFT"):
    return {
        "status": status,
        "title": plan["title"],
        "description": plan["description"],
        "narrator_voice": plan["narrator_voice"],
        "music_style": plan["music_style"],
        "segments": plan["segments"],
    }


def test_edits_narration_then_confirms_and_locks_plan(plan_client):
    client, repository = plan_client
    path = f"/v1/recordings/{repository.recording_id}/podcast-plan"
    generated = client.post(
        f"{path}/draft", json={"narration_style": "warm"}
    ).json()["data"]
    payload = editable_payload(generated["plan"])
    payload["title"] = "会飞的西红柿 · 家庭播客"
    payload["segments"][0]["text"] = "这是一段由家人亲口留下的晚餐声音。"
    draft = client.put(path, json=payload)
    assert draft.status_code == 200
    assert draft.json()["data"]["plan"]["revision"] == 2

    payload = editable_payload(draft.json()["data"]["plan"], "CONFIRMED")
    confirmed = client.put(path, json=payload)
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["plan"]["status"] == "CONFIRMED"

    payload["status"] = "DRAFT"
    locked = client.put(path, json=payload)
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "PODCAST_PLAN_ALREADY_CONFIRMED"


def test_rejects_any_change_to_family_original_quote(plan_client):
    client, repository = plan_client
    base = f"/v1/recordings/{repository.recording_id}/podcast-plan"
    plan = client.post(f"{base}/draft", json={"narration_style": "warm"}).json()["data"]["plan"]
    payload = editable_payload(plan)
    original = next(item for item in payload["segments"] if item["kind"] == "original")
    original["text"] = "被改写的家人原声"
    response = client.put(base, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PODCAST_PLAN_SAFETY_CHECK_FAILED"


def test_creates_short_ai_narration_preview(plan_client):
    client, repository = plan_client
    base = f"/v1/recordings/{repository.recording_id}/podcast-plan"
    plan = client.post(f"{base}/draft", json={"narration_style": "warm"}).json()["data"]["plan"]
    narration = next(item for item in plan["segments"] if item["kind"] == "narration")
    response = client.post(
        f"{base}/narration-preview",
        json={"segment_index": narration["segment_index"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"] == "preview-test"
    assert response.json()["data"]["url"].endswith("/v1/playback/signed-preview")

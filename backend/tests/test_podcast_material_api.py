from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.podcast_material_router import get_podcast_material_repository
from app.podcast_material_repository import PostgresPodcastMaterialRepository


class MemoryPodcastMaterialRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.recording_id = uuid4()
        self.member_id = uuid4()
        self.project_id = uuid4()
        self.version = 1
        self.workspace = None

    def _new_workspace(self):
        now = datetime.now(UTC)
        material_id = uuid4()
        return {
            "id": uuid4(),
            "project_id": self.project_id,
            "podcast_version_id": uuid4(),
            "recording_id": self.recording_id,
            "recording_title": "周日晚餐",
            "recording_duration_ms": 60_000,
            "status": "DRAFT",
            "revision": 1,
            "schema_version": "podcast-material-v1",
            "transcript_revision": 3,
            "materials": [{
                "id": material_id,
                "source_moment_id": uuid4(),
                "source_recording_id": self.recording_id,
                "source_segment_id": uuid4(),
                "family_member_id": None,
                "speaker_key": "speaker_a",
                "speaker_label": "说话人 A",
                "role": "highlight",
                "position": 1,
                "start_ms": 3_200,
                "end_ms": 8_400,
                "original_text": "它飞到奶奶家了",
                "confirmed_text": "它差点飞到奶奶家",
                "share_allowed": True,
            }],
            "family_members": [{"id": self.member_id, "nickname": "苗苗"}],
            "created_at": now,
            "updated_at": now,
        }

    def get_for_user(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        return deepcopy(self.workspace)

    def get_or_create_draft(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        if self.workspace is None or self.workspace["status"] == "CONFIRMED":
            previous = self.workspace
            self.version += 1 if previous else 0
            self.workspace = self._new_workspace()
            if previous:
                self.workspace["materials"] = deepcopy(previous["materials"])
                for material in self.workspace["materials"]:
                    material["id"] = uuid4()
        return deepcopy(self.workspace)

    def update(self, user_id, recording_id, status, materials):
        if (
            user_id != self.user_id
            or recording_id != self.recording_id
            or self.workspace is None
            or self.workspace["status"] != "DRAFT"
        ):
            return None
        current = {item["id"]: item for item in self.workspace["materials"]}
        if not {item["id"] for item in materials}.issubset(current):
            return None
        self.workspace["materials"] = [
            {**current[item["id"]], **item} for item in materials
        ]
        self.workspace["status"] = status
        self.workspace["revision"] += 1
        return deepcopy(self.workspace)


@pytest.fixture()
def material_client():
    user_id = uuid4()
    repository = MemoryPodcastMaterialRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_material_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_creates_draft_from_confirmed_highlights(material_client):
    client, repository = material_client
    response = client.post(
        f"/v1/recordings/{repository.recording_id}/podcast-material-set/draft"
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["materials"][0]["original_text"] == "它飞到奶奶家了"
    assert data["materials"][0]["confirmed_text"] == "它差点飞到奶奶家"


def test_confirmation_allows_unknown_speaker_and_freezes_version(material_client):
    client, repository = material_client
    draft = client.post(
        f"/v1/recordings/{repository.recording_id}/podcast-material-set/draft"
    ).json()["data"]
    confirmed = client.put(
        f"/v1/recordings/{repository.recording_id}/podcast-material-set",
        json={"status": "CONFIRMED", "materials": [{
            "id": draft["materials"][0]["id"],
            "family_member_id": None,
            "speaker_label": "说话人 A",
            "role": "highlight",
            "position": 1,
            "start_ms": 3_200,
            "end_ms": 8_400,
            "confirmed_text": "它差点飞到奶奶家",
            "share_allowed": True,
        }]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"
    assert confirmed.json()["data"]["materials"][0]["family_member_id"] is None

    item = draft["materials"][0]
    locked = client.put(
        f"/v1/recordings/{repository.recording_id}/podcast-material-set",
        json={"status": "DRAFT", "materials": [{
            "id": item["id"],
            "family_member_id": None,
            "speaker_label": "说话人 A",
            "role": "highlight",
            "position": 1,
            "start_ms": item["start_ms"],
            "end_ms": item["end_ms"],
            "confirmed_text": item["confirmed_text"],
            "share_allowed": True,
        }]},
    )
    assert locked.status_code == 404

    next_draft = client.post(
        f"/v1/recordings/{repository.recording_id}/podcast-material-set/draft"
    )
    assert next_draft.status_code == 200
    assert next_draft.json()["data"]["status"] == "DRAFT"
    assert next_draft.json()["data"]["materials"][0]["id"] != item["id"]


def test_other_family_cannot_read_materials(material_client):
    client, _repository = material_client
    response = client.get(f"/v1/recordings/{uuid4()}/podcast-material-set")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PODCAST_MATERIALS_NOT_FOUND"


def test_highlight_quote_selects_its_own_source_segment_not_first_context_line():
    first_id = uuid4()
    highlight_id = uuid4()
    board = {
        "highlight_quote": "哈哈哈哈，先把桌子擦干净。",
        "source_segments": [
            {"transcript_segment_id": str(first_id), "quote": "西红柿差点飞走。"},
            {
                "transcript_segment_id": str(highlight_id),
                "quote": "哈哈哈哈，先把桌子擦干净。",
            },
        ],
    }
    assert PostgresPodcastMaterialRepository.highlight_source_segment_id(board) == str(
        highlight_id
    )

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.moment_router import get_moment_repository


def make_moment(recording_id):
    now = datetime.now(UTC)
    segment_id = uuid4()
    return {
        "id": uuid4(), "recording_id": recording_id, "title": "一家人笑了",
        "theme": "欢乐", "score": 0.88, "rank": 1, "start_ms": 1000, "end_ms": 5000,
        "selection_state": "candidate", "score_breakdown": {"humor": 1.0},
        "storyboard": {
            "schema_version": "1.0", "pipeline_version": "storyboard-v1",
            "title": "一家人笑了", "scene": "晚餐", "story_type": "家庭趣事",
            "characters": [{"family_member_id": None, "speaker_key": "speaker_a", "display_name": "说话人 A"}],
            "setup": "爸爸做汤", "turning_point": "西红柿掉进汤里",
            "ending": "我们都笑了", "highlight_quote": "我们都笑了",
            "emotion_curve": ["日常", "意外", "欢乐"],
            "source_segments": [{"transcript_segment_id": str(segment_id), "start_ms": 1000, "end_ms": 5000, "quote": "我们都笑了"}],
            "sensitive_flags": [], "confidence": 0.88,
        },
        "transcript_revision": 2, "edited_by_user": False,
        "pipeline_version": "storyboard-v1", "created_at": now, "updated_at": now,
    }


class MemoryMomentApiRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.recording_id = uuid4()
        self.moment = make_moment(self.recording_id)

    def list_for_user(self, user_id, recording_id):
        return [self.moment] if user_id == self.user_id and recording_id == self.recording_id else None

    def get_for_user(self, user_id, moment_id):
        return self.moment if user_id == self.user_id and moment_id == self.moment["id"] else None

    def update_for_user(self, user_id, moment_id, selection_state, start_ms, end_ms):
        if self.get_for_user(user_id, moment_id) is None:
            return None
        if selection_state:
            self.moment["selection_state"] = selection_state
        if start_ms is not None:
            self.moment.update(start_ms=start_ms, end_ms=end_ms, edited_by_user=True)
        return self.moment

    def load_source(self, recording_id):
        if recording_id != self.recording_id:
            return None
        source = self.moment["storyboard"]["source_segments"][0]
        return {
            "recording": {"scene_type": "晚餐", "transcript_revision": 2},
            "segments": [{
                "id": source["transcript_segment_id"], "speaker_key": "speaker_a",
                "start_ms": source["start_ms"], "end_ms": source["end_ms"],
                "text": source["quote"], "confidence": 0.88,
            }],
            "speaker_names": {"speaker_a": {"family_member_id": None, "display_name": "说话人 A"}},
        }

    def replace_moments(self, recording_id, moments, pipeline_version, transcript_revision):
        assert recording_id == self.recording_id
        assert pipeline_version == "storyboard-v1"
        assert transcript_revision == 2


@pytest.fixture()
def moment_client():
    user_id = uuid4()
    repository = MemoryMomentApiRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_moment_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_lists_traceable_highlights(moment_client):
    client, repository = moment_client
    response = client.get(f"/v1/recordings/{repository.recording_id}/moments")
    assert response.status_code == 200
    source = response.json()["data"]["moments"][0]["storyboard"]["source_segments"][0]
    assert source["quote"] == "我们都笑了"
    assert source["transcript_segment_id"]


def test_keeps_and_adjusts_highlight(moment_client):
    client, repository = moment_client
    kept = client.patch(f"/v1/moments/{repository.moment['id']}", json={"selection_state": "kept"})
    adjusted = client.patch(
        f"/v1/moments/{repository.moment['id']}", json={"start_ms": 1500, "end_ms": 4500}
    )
    assert kept.json()["data"]["selection_state"] == "kept"
    assert adjusted.json()["data"]["start_ms"] == 1500
    assert adjusted.json()["data"]["edited_by_user"] is True


def test_other_family_cannot_read_moment(moment_client):
    client, _repository = moment_client
    response = client.get(f"/v1/moments/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MOMENT_NOT_FOUND"


def test_rebuilds_highlights_after_transcript_correction(moment_client):
    client, repository = moment_client
    response = client.post(f"/v1/recordings/{repository.recording_id}/moments/rebuild")
    assert response.status_code == 200

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.comic_repository import PostgresComicRepository
from app.comic_router import get_comic_repository, require_comic_creation_enabled
from app.main import app


def make_comic(moment_id):
    now = datetime.now(UTC)
    comic_id = uuid4()
    panels = []
    for index in range(1, 5):
        panels.append({
            "id": uuid4(), "panel_index": index, "narration": f"第 {index} 格",
            "dialogue": "我们都笑了" if index == 2 else None,
            "source_segment_id": uuid4() if index == 2 else None,
            "asset_url": "/assets/comics/family-dinner-four-panel-v1.png",
            "asset_variant": "composite-v1", "crop_x": (index - 1) % 2,
            "crop_y": (index - 1) // 2, "prompt": f"panel {index}", "version": 1,
            "created_at": now, "updated_at": now,
        })
    return {
        "id": comic_id, "moment_id": moment_id, "title": "家庭晚餐",
        "status": "COMPLETED", "version": 1, "pipeline_version": "storyboard-v1",
        "metadata": {"layout": "2x2", "visual_bible": {"characters": []}},
        "panels": panels, "created_at": now, "updated_at": now,
    }


class MemoryComicRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.moment_id = uuid4()
        self.comic = make_comic(self.moment_id)

    def create_for_moment(self, user_id, moment_id, _pipeline_version):
        return self.comic if user_id == self.user_id and moment_id == self.moment_id else None

    def get_for_user(self, user_id, comic_id):
        return self.comic if user_id == self.user_id and comic_id == self.comic["id"] else None

    def regenerate_panel(self, user_id, comic_id, panel_index):
        if self.get_for_user(user_id, comic_id) is None or panel_index not in range(1, 5):
            return None
        self.comic["version"] += 1
        panel = self.comic["panels"][panel_index - 1]
        panel["version"] += 1
        panel["asset_variant"] = f"panel-{panel_index}-v{panel['version']}"
        return self.comic


@pytest.fixture()
def comic_client():
    user_id = uuid4()
    repository = MemoryComicRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_comic_repository] = lambda: repository
    app.dependency_overrides[require_comic_creation_enabled] = lambda: None
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_creates_four_panel_comic_from_kept_moment(comic_client):
    client, repository = comic_client
    response = client.post(f"/v1/moments/{repository.moment_id}/comics")
    assert response.status_code == 200
    assert len(response.json()["data"]["panels"]) == 4
    assert response.json()["data"]["metadata"]["layout"] == "2x2"


def test_single_panel_regeneration_preserves_other_versions(comic_client):
    client, repository = comic_client
    before = [item["version"] for item in repository.comic["panels"]]
    response = client.post(
        f"/v1/comics/{repository.comic['id']}/panels/2/regenerate"
    )
    after = [item["version"] for item in response.json()["data"]["panels"]]
    assert after == [before[0], before[1] + 1, before[2], before[3]]


def test_other_family_cannot_read_comic(comic_client):
    client, _repository = comic_client
    response = client.get(f"/v1/comics/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COMIC_NOT_FOUND"


def test_comic_creation_feature_flag_keeps_legacy_reads_but_blocks_new_work(monkeypatch):
    monkeypatch.setattr(
        "app.comic_router.get_settings",
        lambda: SimpleNamespace(comic_creation_enabled=False),
    )
    with pytest.raises(HTTPException) as exc:
        require_comic_creation_enabled()
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "COMIC_CREATION_DISABLED"


def test_single_source_quote_is_used_once_and_only_as_dialogue():
    segment_id = uuid4()
    storyboard = {
        "scene": "家庭晚餐",
        "characters": [{"display_name": "爸爸", "speaker_key": "SPEAKER_01"}],
        "setup": "一家人坐在餐桌边。",
        "turning_point": "爸爸夹菜时手一滑。",
        "ending": "大家一起笑了起来。",
        "source_segments": [{
            "transcript_segment_id": str(segment_id),
            "quote": "爸爸把西红柿掉进了汤里，我们都笑了。",
        }],
    }

    panels = PostgresComicRepository._panel_specs(storyboard)

    assert [panel["dialogue"] for panel in panels].count(
        "爸爸把西红柿掉进了汤里，我们都笑了。"
    ) == 1
    assert panels[1]["source_segment_id"] == str(segment_id)
    assert all(
        "爸爸把西红柿掉进了汤里，我们都笑了。" not in panel["narration"]
        for panel in panels
    )
    assert all(
        panel["source_segment_id"] is None
        for index, panel in enumerate(panels)
        if index != 1
    )

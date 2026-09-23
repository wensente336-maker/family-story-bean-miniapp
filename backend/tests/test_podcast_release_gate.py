from copy import deepcopy
from time import perf_counter
from uuid import uuid4

import pytest

from app.podcast_render_service import PodcastRenderService


class ReplayRepository:
    def __init__(self, scene: str, failure: str | None = None):
        self.job_id = uuid4()
        self.family_id = uuid4()
        self.recording_id = uuid4()
        self.version_id = uuid4()
        self.material_id = uuid4()
        self.failure = failure
        self.status = "CREATED"
        self.retry_count = 0
        quote = {
            "humorous": "番茄说它差点飞到奶奶家。",
            "warm": "妈妈说，回家吃饭就好。",
            "growth": "今天我终于学会自己系鞋带了。",
        }[scene]
        self.context = {
            "family_id": self.family_id, "recording_id": self.recording_id,
            "podcast_version_id": self.version_id, "version": 1,
            "source_object_key": f"recordings/{self.recording_id}/source.wav",
            "music_style": "warm-acoustic-light", "plan_revision": 1,
            "plan": {"segments": [
                {"kind": "narration", "label": "开场", "text": "故事开始。", "source_material_ids": [str(self.material_id)]},
                {"kind": "original", "label": "家人原声", "text": quote, "source_material_ids": [str(self.material_id)]},
                {"kind": "narration", "label": "收尾", "text": "声音被收藏。", "source_material_ids": [str(self.material_id)]},
            ]},
            "materials": [{
                "id": self.material_id, "source_segment_id": uuid4(),
                "start_ms": 897000, "end_ms": 900000, "confirmed_text": quote,
                "speaker_label": "家人", "position": 1,
            }],
        }
        self.completed = None

    def claim(self, job_id, token):
        if self.failure == "queue_interruption" or self.status not in {"CREATED", "FAILED"}:
            return None
        self.status = "GENERATING"
        return {"id": job_id}

    def load_context(self, _job_id):
        context = deepcopy(self.context)
        if self.failure == "missing_storage":
            context["source_object_key"] = None
        return context

    def update_progress(self, *_args):
        return None

    def complete(self, job_id, token, object_key, metadata):
        self.status = "COMPLETED"
        self.completed = {
            "job": {"id": job_id, "status": "COMPLETED"},
            "object_key": object_key, "render_metadata": metadata,
        }
        return deepcopy(self.completed)

    def fail(self, job_id, token, code, detail):
        self.status = "FAILED"; self.retry_count += 1
        return {"job": {"id": job_id, "status": "FAILED"}}


class ReplayRenderer:
    def __init__(self, degraded=False, fail=False):
        self.degraded = degraded
        self.fail = fail
        self.segments = []

    def render(self, source, destination, segments, music_style):
        if self.fail:
            raise RuntimeError("injected renderer failure")
        self.segments = deepcopy(segments)
        return {
            "duration_ms": 128000,
            "render_mode": "original_only" if self.degraded else "narrated",
            "tts_fallback_used": self.degraded,
            "timeline": [], "music_style": music_style,
        }


def test_release_gate_replays_thirty_complete_generations_under_local_p95():
    durations = []
    first_pass = usable = traceable = 0
    for index in range(30):
        scene = ("humorous", "warm", "growth")[index % 3]
        repository = ReplayRepository(scene)
        renderer = ReplayRenderer(degraded=index in {13, 27})
        started = perf_counter()
        result = PodcastRenderService(repository, renderer).run(repository.job_id)
        durations.append(perf_counter() - started)
        usable += result["job"]["status"] == "COMPLETED"
        first_pass += result["render_metadata"]["render_mode"] == "narrated"
        original = next(item for item in renderer.segments if item["kind"] == "original")
        traceable += (
            original["text"] == repository.context["materials"][0]["confirmed_text"]
            and original["source_segment_id"] == repository.context["materials"][0]["source_segment_id"]
        )
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert first_pass / 30 >= 0.90
    assert usable / 30 >= 0.98
    assert traceable == 30
    assert p95 < 180


@pytest.mark.parametrize("attempt", range(10))
def test_tts_failure_degrades_to_usable_original_only(attempt):
    repository = ReplayRepository("warm")
    result = PodcastRenderService(repository, ReplayRenderer(degraded=True)).run(repository.job_id)
    assert result["job"]["status"] == "COMPLETED"
    assert result["render_metadata"]["render_mode"] == "original_only"


@pytest.mark.parametrize("failure", ["missing_storage", "renderer"])
@pytest.mark.parametrize("attempt", range(10))
def test_storage_and_renderer_failures_are_retryable_without_false_completion(failure, attempt):
    repository = ReplayRepository("growth", failure="missing_storage" if failure == "missing_storage" else None)
    result = PodcastRenderService(
        repository, ReplayRenderer(fail=failure == "renderer")
    ).run(repository.job_id)
    assert result["status"] == "FAILED"
    assert repository.status == "FAILED"
    assert repository.completed is None
    assert repository.retry_count == 1


@pytest.mark.parametrize("attempt", range(10))
def test_queue_interruption_is_idempotently_skipped(attempt):
    repository = ReplayRepository("humorous", failure="queue_interruption")
    result = PodcastRenderService(repository, ReplayRenderer()).run(repository.job_id)
    assert result["status"] == "DUPLICATE_SKIPPED"
    assert repository.completed is None

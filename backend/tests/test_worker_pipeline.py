from uuid import uuid4

import pytest

from app.config import Settings
from app.job_service import CeleryJobDispatcher, QueueUnavailableError
from worker import main as worker_main


class MemoryPipelineRepository:
    def __init__(self):
        self.claimed = False
        self.stages: list[tuple[str, int]] = []
        self.queue_error: str | None = None
        self.recording_id = uuid4()

    def claim(self, _job_id, _token, _stale_after):
        if self.claimed:
            return None
        self.claimed = True
        return {"id": _job_id, "recording_id": self.recording_id, "stage": "PREPROCESSING"}

    def update_stage(self, job_id, _token, stage, progress):
        self.stages.append((stage, progress))
        return {"id": job_id, "stage": stage, "progress": progress}

    def mark_queue_attempt(self, _job_id, error_code=None):
        self.queue_error = error_code

    def heartbeat(self, _job_id, _token):
        pass


def test_pipeline_runs_complete_state_machine_without_real_asr(monkeypatch) -> None:
    repository = MemoryPipelineRepository()
    monkeypatch.setattr(worker_main.settings, "pipeline_demo_step_seconds", 0)
    result = worker_main.run_pipeline(
        uuid4(), "execution-1", repository, sleeper=lambda _seconds: None
    )
    assert repository.stages == [
        ("PREPROCESSING", 25),
        ("TRANSCRIBING", 40),
        ("TRANSCRIBING", 50),
        ("ANALYZING", 75),
        ("READY_FOR_SELECTION", 100),
    ]
    assert result["status"] == "READY_FOR_SELECTION"


def test_duplicate_delivery_is_skipped_after_first_claim(monkeypatch) -> None:
    repository = MemoryPipelineRepository()
    monkeypatch.setattr(worker_main.settings, "pipeline_demo_step_seconds", 0)
    job_id = uuid4()
    worker_main.run_pipeline(job_id, "same-task", repository, sleeper=lambda _seconds: None)
    duplicate = worker_main.run_pipeline(
        job_id, "same-task", repository, sleeper=lambda _seconds: None
    )
    assert duplicate["status"] == "DUPLICATE_SKIPPED"
    assert len(repository.stages) == 5


def test_real_pipeline_runs_transcription_before_moment_discovery(monkeypatch) -> None:
    repository = MemoryPipelineRepository()
    calls = []

    class Pipeline:
        def __init__(self, name):
            self.name = name

        def process(self, recording_id):
            calls.append((self.name, recording_id))

    monkeypatch.setattr(worker_main.settings, "pipeline_demo_step_seconds", 0)
    result = worker_main.run_pipeline(
        uuid4(), "execution-1", repository, sleeper=lambda _seconds: None,
        transcription_pipeline=Pipeline("transcription"),
        moment_pipeline=Pipeline("moments"),
    )
    assert calls == [
        ("transcription", repository.recording_id),
        ("moments", repository.recording_id),
    ]
    assert result["status"] == "READY_FOR_SELECTION"


def test_fault_injection_can_target_a_pipeline_stage(monkeypatch) -> None:
    repository = MemoryPipelineRepository()
    monkeypatch.setattr(worker_main.settings, "allow_task_fault_injection", True)
    monkeypatch.setattr(worker_main.settings, "pipeline_demo_step_seconds", 0)
    with pytest.raises(RuntimeError, match="TRANSCRIBING"):
        worker_main.run_pipeline(
            uuid4(), "execution-1", repository,
            sleeper=lambda _seconds: None, fault_stage="TRANSCRIBING",
        )


def test_pause_switch_keeps_job_created_without_dispatch() -> None:
    repository = MemoryPipelineRepository()
    dispatcher = CeleryJobDispatcher(
        Settings(pipeline_accept_new_jobs=False), repository
    )
    assert dispatcher.enqueue(uuid4()) is False
    assert repository.queue_error == "PIPELINE_PAUSED"


def test_queue_outage_is_visible_and_a_later_enqueue_recovers(monkeypatch) -> None:
    repository = MemoryPipelineRepository()
    dispatcher = CeleryJobDispatcher(
        Settings(pipeline_accept_new_jobs=True), repository
    )
    job_id = uuid4()

    def unavailable(**_kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(worker_main.process_recording, "apply_async", unavailable)
    with pytest.raises(QueueUnavailableError):
        dispatcher.enqueue(job_id)
    assert repository.queue_error == "QUEUE_UNAVAILABLE"

    monkeypatch.setattr(
        worker_main.process_recording, "apply_async", lambda **_kwargs: object()
    )
    assert dispatcher.enqueue(job_id) is True
    assert repository.queue_error is None

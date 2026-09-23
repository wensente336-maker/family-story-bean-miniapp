from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.job_router import get_job_dispatcher, get_job_repository
from app.main import app


class MemoryJobRepository:
    def __init__(self, user_id):
        now = datetime.now(UTC)
        self.user_id = user_id
        self.recording_id = uuid4()
        self.job = {
            "id": uuid4(),
            "recording_id": self.recording_id,
            "stage": "CREATED",
            "progress": 0,
            "retry_count": 0,
            "pipeline_version": "storyboard-v1",
            "error_code": None,
            "error_detail": {},
            "heartbeat_at": None,
            "queue_attempted_at": None,
            "started_at": None,
            "completed_at": None,
            "dead_lettered_at": None,
            "created_at": now,
            "updated_at": now,
        }

    def get_for_user(self, user_id, job_id):
        return self.job if user_id == self.user_id and job_id == self.job["id"] else None

    def get_by_recording_for_user(self, user_id, recording_id):
        if user_id == self.user_id and recording_id == self.recording_id:
            return self.job
        return None

    def reset_for_manual_retry(self, user_id, job_id):
        if self.get_for_user(user_id, job_id) is None or self.job["stage"] != "FAILED":
            return None
        self.job.update(stage="CREATED", progress=0, retry_count=0, error_code=None)
        return self.job


class MemoryDispatcher:
    def __init__(self, repository):
        self.repository = repository
        self.enqueued = []

    def enqueue(self, job_id):
        self.enqueued.append(job_id)
        self.repository.job["queue_attempted_at"] = datetime.now(UTC)
        self.repository.job["error_code"] = None
        return True


@pytest.fixture()
def jobs_client():
    user_id = uuid4()
    repository = MemoryJobRepository(user_id)
    dispatcher = MemoryDispatcher(repository)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_job_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        yield client, repository, dispatcher
    app.dependency_overrides.clear()


def test_polling_created_job_opportunistically_requeues(jobs_client) -> None:
    client, repository, dispatcher = jobs_client
    response = client.get(f"/v1/jobs/{repository.job['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "CREATED"
    assert dispatcher.enqueued == [repository.job["id"]]
    second_response = client.get(f"/v1/jobs/{repository.job['id']}")
    assert second_response.status_code == 200
    assert dispatcher.enqueued == [repository.job["id"]]


def test_recording_job_lookup_and_pipeline_status(jobs_client) -> None:
    client, repository, _dispatcher = jobs_client
    job_response = client.get(f"/v1/recordings/{repository.recording_id}/job")
    status_response = client.get("/v1/pipeline/status")
    assert job_response.status_code == 200
    assert job_response.json()["data"]["recording_id"] == str(repository.recording_id)
    assert status_response.status_code == 200
    assert status_response.json()["data"]["max_automatic_retries"] == 2


def test_failed_job_can_be_manually_retried(jobs_client) -> None:
    client, repository, dispatcher = jobs_client
    repository.job.update(
        stage="FAILED", progress=50, retry_count=2, error_code="PIPELINE_STEP_FAILED"
    )
    response = client.post(f"/v1/jobs/{repository.job['id']}/retry")
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "CREATED"
    assert response.json()["data"]["retry_count"] == 0
    assert dispatcher.enqueued == [repository.job["id"]]

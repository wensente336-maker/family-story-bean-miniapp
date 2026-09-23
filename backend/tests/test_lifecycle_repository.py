from uuid import uuid4

from app.lifecycle_repository import PostgresLifecycleRepository


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, expired_rows):
        self.expired_rows = expired_rows
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.statements.append((" ".join(statement.split()), parameters))
        if "FROM recordings" in statement and "SKIP LOCKED" in statement:
            return FakeResult(self.expired_rows)
        return FakeResult()


class FakeStorage:
    def __init__(self):
        self.deleted = []

    def delete(self, object_key):
        self.deleted.append(object_key)


def test_expired_originals_are_deleted_without_deleting_derived_records():
    recording_id, family_id = uuid4(), uuid4()
    connection = FakeConnection([{
        "id": recording_id,
        "family_id": family_id,
        "object_key": "families/family/recordings/recording/source",
    }])
    storage = FakeStorage()
    repository = PostgresLifecycleRepository("postgresql://unused", storage)
    repository._connect = lambda: connection

    result = repository.purge_expired_originals()

    assert result == {"purged": 1}
    assert storage.deleted == ["families/family/recordings/recording/source"]
    sql = " ".join(statement for statement, _parameters in connection.statements)
    assert "SET object_key=NULL,delete_at=NULL" in sql
    assert "ORIGINAL_AUDIO_EXPIRY" in sql
    assert "DELETE FROM recordings" not in sql


def test_podcast_deletion_expands_all_rendered_versions():
    keys = PostgresLifecycleRepository._creation_object_keys({
        "object_key": "families/f/recordings/r/podcasts/p/v3.mp3",
        "creation_type": "PODCAST",
        "version": 3,
    })
    assert keys == [
        "families/f/recordings/r/podcasts/p/v1.mp3",
        "families/f/recordings/r/podcasts/p/v2.mp3",
        "families/f/recordings/r/podcasts/p/v3.mp3",
    ]

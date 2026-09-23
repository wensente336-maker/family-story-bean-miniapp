from uuid import uuid4

import pytest

from app.security import InvalidTokenError, decode_access_token, issue_access_token


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    token, _ = issue_access_token(user_id, "test-key", 60)
    assert decode_access_token(token, "test-key").user_id == user_id


def test_tampered_or_expired_token_is_rejected() -> None:
    user_id = uuid4()
    token, expires_at = issue_access_token(user_id, "test-key", 60)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "tampered", "test-key")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, "test-key", now=expires_at)

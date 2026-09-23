from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_access_token(user_id: UUID, signing_key: str, ttl_seconds: int) -> tuple[str, int]:
    expires_at = int(time.time()) + ttl_seconds
    payload = _b64encode(
        json.dumps(
            {"sub": str(user_id), "exp": expires_at, "v": 1},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = _b64encode(
        hmac.new(signing_key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}", expires_at


def decode_access_token(token: str, signing_key: str, now: int | None = None) -> TokenClaims:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(
            hmac.new(signing_key.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise InvalidTokenError("invalid signature")
        data = json.loads(_b64decode(payload))
        user_id = UUID(data["sub"])
        expires_at = int(data["exp"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidTokenError("malformed token") from exc

    if expires_at <= (int(time.time()) if now is None else now):
        raise InvalidTokenError("expired token")
    return TokenClaims(user_id=user_id, expires_at=expires_at)


def hash_openid(openid: str, signing_key: str) -> str:
    return hmac.new(
        signing_key.encode("utf-8"), openid.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hash_phone(phone: str, signing_key: str) -> str:
    return hmac.new(
        signing_key.encode("utf-8"), f"phone:{phone}".encode("utf-8"), hashlib.sha256
    ).hexdigest()

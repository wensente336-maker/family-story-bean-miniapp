from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import Request

from .config import Settings


class InvalidUploadToken(ValueError):
    pass


class UploadTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class UploadClaims:
    recording_id: UUID
    object_key: str
    expires_at: int


@dataclass(frozen=True)
class PlaybackClaims:
    recording_id: UUID
    object_key: str
    expires_at: int
    media_type: str
    share_token: str | None = None


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class LocalObjectStorage:
    def __init__(self, settings: Settings):
        self.root = Path(settings.local_object_storage_path).resolve()
        self.signing_key = settings.auth_signing_key
        self.ttl_seconds = settings.upload_token_ttl_seconds
        self.max_bytes = settings.max_audio_bytes
        self.playback_ttl_seconds = settings.playback_token_ttl_seconds

    def issue_upload_token(self, recording_id: UUID, object_key: str) -> tuple[str, int]:
        expires_at = int(time.time()) + self.ttl_seconds
        payload = _encode(json.dumps(
            {"rid": str(recording_id), "key": object_key, "exp": expires_at, "v": 1, "use": "upload"},
            separators=(",", ":"),
        ).encode())
        signature = _encode(hmac.new(
            self.signing_key.encode(), payload.encode("ascii"), hashlib.sha256
        ).digest())
        return f"{payload}.{signature}", expires_at

    def verify_upload_token(self, token: str) -> UploadClaims:
        try:
            payload, signature = token.split(".", 1)
            expected = _encode(hmac.new(
                self.signing_key.encode(), payload.encode("ascii"), hashlib.sha256
            ).digest())
            if not hmac.compare_digest(signature, expected):
                raise InvalidUploadToken("invalid signature")
            data = json.loads(_decode(payload))
            if data.get("use") != "upload":
                raise InvalidUploadToken("invalid token use")
            claims = UploadClaims(UUID(data["rid"]), data["key"], int(data["exp"]))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidUploadToken("malformed token") from exc
        if claims.expires_at <= int(time.time()):
            raise InvalidUploadToken("expired token")
        expected_prefix = f"recordings/{claims.recording_id}/"
        if f"/{expected_prefix}" not in f"/{claims.object_key}":
            raise InvalidUploadToken("invalid object key")
        return claims

    def issue_playback_token(
        self, recording_id: UUID, object_key: str, media_type: str = "application/octet-stream",
        *, share_token: str | None = None,
    ) -> tuple[str, int]:
        expires_at = int(time.time()) + self.playback_ttl_seconds
        payload = _encode(json.dumps(
            {
                "rid": str(recording_id), "key": object_key, "exp": expires_at,
                "v": 1, "use": "play", "mt": media_type,
                "share": share_token,
            },
            separators=(",", ":"),
        ).encode())
        signature = _encode(hmac.new(
            self.signing_key.encode(), payload.encode("ascii"), hashlib.sha256
        ).digest())
        return f"{payload}.{signature}", expires_at

    def verify_playback_token(self, token: str) -> PlaybackClaims:
        try:
            payload, signature = token.split(".", 1)
            expected = _encode(hmac.new(
                self.signing_key.encode(), payload.encode("ascii"), hashlib.sha256
            ).digest())
            if not hmac.compare_digest(signature, expected):
                raise InvalidUploadToken("invalid signature")
            data = json.loads(_decode(payload))
            if data.get("use") != "play":
                raise InvalidUploadToken("invalid token use")
            claims = PlaybackClaims(
                UUID(data["rid"]), data["key"], int(data["exp"]),
                str(data.get("mt", "application/octet-stream")),
                data.get("share"),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidUploadToken("malformed token") from exc
        if claims.expires_at <= int(time.time()):
            raise InvalidUploadToken("expired token")
        expected_prefix = f"recordings/{claims.recording_id}/"
        if f"/{expected_prefix}" not in f"/{claims.object_key}":
            raise InvalidUploadToken("invalid object key")
        return claims

    def path_for(self, object_key: str) -> Path:
        path = (self.root / object_key).resolve()
        if self.root not in path.parents:
            raise InvalidUploadToken("unsafe object key")
        return path

    async def put(self, request: Request, object_key: str) -> tuple[int, str]:
        destination = self.path_for(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".uploading")
        size = 0
        digest = hashlib.sha256()
        try:
            with temporary.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise UploadTooLarge("audio exceeds size limit")
                    digest.update(chunk)
                    stream.write(chunk)
            if size == 0:
                raise ValueError("empty upload")
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return size, digest.hexdigest()

    def delete(self, object_key: str) -> None:
        self.path_for(object_key).unlink(missing_ok=True)

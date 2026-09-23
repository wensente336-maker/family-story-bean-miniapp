import pytest

from app.config import Settings
from app.otp import OtpInvalidError, OtpRateLimitedError, RedisOtpService


class MemoryRedis:
    def __init__(self):
        self.values: dict[str, str] = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)

    def incr(self, key):
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    def expire(self, key, seconds):
        return key in self.values


def build_service() -> RedisOtpService:
    service = RedisOtpService(
        Settings(
            allow_dev_web_otp=True,
            web_otp_dev_code="123456",
            auth_signing_key="test-signing-key",
        )
    )
    service.redis = MemoryRedis()
    return service


def test_otp_request_is_rate_limited_and_code_is_single_use() -> None:
    service = build_service()
    service.request("phone-hash")
    with pytest.raises(OtpRateLimitedError):
        service.request("phone-hash")

    service.verify("phone-hash", "123456")
    with pytest.raises(OtpInvalidError):
        service.verify("phone-hash", "123456")


def test_five_wrong_attempts_invalidate_the_challenge() -> None:
    service = build_service()
    service.request("another-phone")
    for _ in range(5):
        with pytest.raises(OtpInvalidError):
            service.verify("another-phone", "000000")
    with pytest.raises(OtpInvalidError):
        service.verify("another-phone", "123456")

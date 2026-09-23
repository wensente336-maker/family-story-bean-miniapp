from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from redis import Redis

from .config import Settings


class OtpRateLimitedError(ValueError):
    pass


class OtpInvalidError(ValueError):
    pass


class OtpDeliveryUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OtpChallenge:
    expires_in: int
    resend_after: int
    delivery_hint: str | None = None


class RedisOtpService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    def _digest(self, code: str) -> str:
        return hmac.new(
            self.settings.auth_signing_key.encode("utf-8"),
            f"otp:{code}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def request(self, phone_hash: str) -> OtpChallenge:
        rate_key = f"web-otp:rate:{phone_hash}"
        if not self.redis.set(rate_key, "1", ex=self.settings.web_otp_resend_seconds, nx=True):
            raise OtpRateLimitedError("OTP requested too frequently")

        if not self.settings.allow_dev_web_otp or not self.settings.web_otp_dev_code:
            self.redis.delete(rate_key)
            raise OtpDeliveryUnavailableError("SMS provider is not configured")

        self.redis.set(
            f"web-otp:challenge:{phone_hash}",
            self._digest(self.settings.web_otp_dev_code),
            ex=self.settings.web_otp_ttl_seconds,
        )
        self.redis.delete(f"web-otp:attempts:{phone_hash}")
        return OtpChallenge(
            expires_in=self.settings.web_otp_ttl_seconds,
            resend_after=self.settings.web_otp_resend_seconds,
            delivery_hint=f"开发验证码：{self.settings.web_otp_dev_code}",
        )

    def verify(self, phone_hash: str, code: str) -> None:
        challenge_key = f"web-otp:challenge:{phone_hash}"
        expected = self.redis.get(challenge_key)
        if expected is None:
            raise OtpInvalidError("OTP is missing or expired")

        if not hmac.compare_digest(expected, self._digest(code)):
            attempts_key = f"web-otp:attempts:{phone_hash}"
            attempts = self.redis.incr(attempts_key)
            self.redis.expire(attempts_key, self.settings.web_otp_ttl_seconds)
            if attempts >= 5:
                self.redis.delete(challenge_key, attempts_key)
            raise OtpInvalidError("OTP is invalid")

        self.redis.delete(challenge_key, f"web-otp:attempts:{phone_hash}")

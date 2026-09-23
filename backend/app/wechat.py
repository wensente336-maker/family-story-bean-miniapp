from dataclasses import dataclass

import httpx

from .config import Settings


class WechatLoginError(ValueError):
    pass


@dataclass(frozen=True)
class WechatIdentity:
    openid: str


class WechatCodeExchange:
    endpoint = "https://api.weixin.qq.com/sns/jscode2session"

    def __init__(self, settings: Settings):
        self.settings = settings

    def exchange(self, code: str) -> WechatIdentity:
        if self.settings.allow_dev_wechat_login and code.startswith("dev:"):
            identity = code.removeprefix("dev:").strip()
            if not identity:
                raise WechatLoginError("empty development identity")
            return WechatIdentity(openid=f"dev-openid:{identity}")

        if not self.settings.wechat_app_id or not self.settings.wechat_app_secret:
            raise WechatLoginError("wechat credentials are not configured")

        response = httpx.get(
            self.endpoint,
            params={
                "appid": self.settings.wechat_app_id,
                "secret": self.settings.wechat_app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if "openid" not in payload:
            raise WechatLoginError(payload.get("errmsg", "wechat code exchange failed"))
        return WechatIdentity(openid=payload["openid"])

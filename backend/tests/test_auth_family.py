from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import get_otp_service, get_repository, get_wechat_exchange
from app.main import app
from app.otp import OtpChallenge, OtpInvalidError
from app.recording_router import get_recording_repository
from app.job_router import get_job_repository
from app.wechat import WechatIdentity


class FakeWechatExchange:
    def exchange(self, code: str) -> WechatIdentity:
        if not code.startswith("test:"):
            raise ValueError("invalid test code")
        return WechatIdentity(openid=code)


class FakeOtpService:
    def __init__(self):
        self.challenges: set[str] = set()

    def request(self, phone_hash: str) -> OtpChallenge:
        self.challenges.add(phone_hash)
        return OtpChallenge(expires_in=300, resend_after=60, delivery_hint="开发验证码：123456")

    def verify(self, phone_hash: str, code: str) -> None:
        if code != "123456" or phone_hash not in self.challenges:
            raise OtpInvalidError("invalid")
        self.challenges.remove(phone_hash)


class MemoryFamilyRepository:
    def __init__(self):
        self.users_by_hash: dict[str, dict] = {}
        self.users: dict[UUID, dict] = {}
        self.families: dict[UUID, dict] = {}

    @staticmethod
    def _now():
        return datetime.now(UTC)

    def upsert_user(self, openid_hash: str) -> dict:
        if openid_hash not in self.users_by_hash:
            now = self._now()
            user = {"id": uuid4(), "status": "ACTIVE", "created_at": now, "updated_at": now}
            self.users_by_hash[openid_hash] = user
            self.users[user["id"]] = user
        return self.users_by_hash[openid_hash]

    def upsert_phone_user(self, phone_hash: str) -> dict:
        return self.upsert_user(f"phone:{phone_hash}")

    def get_user(self, user_id: UUID) -> dict | None:
        return self.users.get(user_id)

    def get_family_for_user(self, user_id: UUID) -> dict | None:
        return next(
            (family for family in self.families.values() if family["owner_user_id"] == user_id),
            None,
        )

    def latest_recording(self, _user_id: UUID) -> None:
        return None

    def latest_for_user(self, _user_id: UUID) -> None:
        return None

    def create_family(self, user_id: UUID, name: str, owner_nickname: str) -> dict:
        now = self._now()
        family_id = uuid4()
        family = {
            "id": family_id,
            "owner_user_id": user_id,
            "name": name,
            "members": [self._member(owner_nickname)],
            "created_at": now,
            "updated_at": now,
        }
        self.families[family_id] = family
        return family

    def get_family(self, user_id: UUID, family_id: UUID) -> dict | None:
        family = self.families.get(family_id)
        return family if family and family["owner_user_id"] == user_id else None

    def rename_family(self, user_id: UUID, family_id: UUID, name: str) -> dict | None:
        family = self.get_family(user_id, family_id)
        if family:
            family["name"] = name
            family["updated_at"] = self._now()
        return family

    def add_member(self, user_id: UUID, family_id: UUID, nickname: str) -> dict | None:
        family = self.get_family(user_id, family_id)
        if not family:
            return None
        member = self._member(nickname)
        family["members"].append(member)
        return member

    def rename_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID, nickname: str
    ) -> dict | None:
        family = self.get_family(user_id, family_id)
        if not family:
            return None
        for member in family["members"]:
            if member["id"] == member_id:
                member["nickname"] = nickname
                member["updated_at"] = self._now()
                return member
        return None

    def delete_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID
    ) -> dict | None:
        family = self.get_family(user_id, family_id)
        if not family or not family["members"] or family["members"][0]["id"] == member_id:
            return None
        before = len(family["members"])
        family["members"] = [member for member in family["members"] if member["id"] != member_id]
        return family if len(family["members"]) < before else None

    def _member(self, nickname: str) -> dict:
        now = self._now()
        return {
            "id": uuid4(),
            "nickname": nickname,
            "character_profile": {},
            "voice_consent": False,
            "created_at": now,
            "updated_at": now,
        }


@pytest.fixture()
def client_and_repo():
    repository = MemoryFamilyRepository()
    otp_service = FakeOtpService()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_wechat_exchange] = lambda: FakeWechatExchange()
    app.dependency_overrides[get_otp_service] = lambda: otp_service
    app.dependency_overrides[get_recording_repository] = lambda: repository
    app.dependency_overrides[get_job_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def login(client: TestClient, identity: str) -> dict:
    response = client.post("/v1/auth/wechat", json={"code": f"test:{identity}"})
    assert response.status_code == 200
    return response.json()["data"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def phone_login(client: TestClient, phone: str = "13800138000") -> dict:
    requested = client.post("/v1/auth/otp/request", json={"phone": phone})
    assert requested.status_code == 200
    verified = client.post(
        "/v1/auth/otp/verify", json={"phone": phone, "code": "123456"}
    )
    assert verified.status_code == 200
    return verified.json()["data"]


def test_unauthenticated_family_request_is_rejected(client_and_repo) -> None:
    client, _ = client_and_repo
    response = client.get(f"/v1/families/{uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_first_login_creates_family_and_twenty_reentries_restore_it(client_and_repo) -> None:
    client, _ = client_and_repo
    first = login(client, "parent-a")
    assert first["family"] is None

    created = client.post(
        "/v1/families",
        headers=auth(first["access_token"]),
        json={"name": "小满一家", "owner_nickname": "妈妈"},
    )
    assert created.status_code == 201
    family_id = created.json()["data"]["id"]

    for _ in range(20):
        signed_in = login(client, "parent-a")
        restored = client.get("/v1/session", headers=auth(signed_in["access_token"]))
        assert restored.status_code == 200
        assert restored.json()["data"]["family"]["id"] == family_id


def test_two_families_cannot_access_each_other(client_and_repo) -> None:
    client, _ = client_and_repo
    first = login(client, "parent-a")
    second = login(client, "parent-b")
    family_a = client.post(
        "/v1/families",
        headers=auth(first["access_token"]),
        json={"name": "A 家", "owner_nickname": "A"},
    ).json()["data"]
    family_b = client.post(
        "/v1/families",
        headers=auth(second["access_token"]),
        json={"name": "B 家", "owner_nickname": "B"},
    ).json()["data"]

    attempts = []
    for _ in range(10):
        attempts.append(
            client.get(f"/v1/families/{family_b['id']}", headers=auth(first["access_token"]))
        )
        attempts.append(
            client.get(f"/v1/families/{family_a['id']}", headers=auth(second["access_token"]))
        )
    assert all(response.status_code == 404 for response in attempts)
    assert all(response.json()["error"]["code"] == "FAMILY_NOT_FOUND" for response in attempts)


def test_family_and_member_names_can_be_updated(client_and_repo) -> None:
    client, _ = client_and_repo
    signed_in = login(client, "parent-a")
    headers = auth(signed_in["access_token"])
    family = client.post(
        "/v1/families",
        headers=headers,
        json={"name": "旧名字", "owner_nickname": "妈妈"},
    ).json()["data"]
    renamed = client.patch(
        f"/v1/families/{family['id']}", headers=headers, json={"name": "新名字"}
    )
    assert renamed.json()["data"]["name"] == "新名字"

    member = client.post(
        f"/v1/families/{family['id']}/members", headers=headers, json={"nickname": "宝宝"}
    ).json()["data"]
    renamed_member = client.patch(
        f"/v1/families/{family['id']}/members/{member['id']}",
        headers=headers,
        json={"nickname": "小满"},
    )
    assert renamed_member.json()["data"]["nickname"] == "小满"


def test_family_member_can_be_deleted_but_creator_is_protected(client_and_repo) -> None:
    client, _ = client_and_repo
    signed_in = login(client, "parent-delete")
    headers = auth(signed_in["access_token"])
    family = client.post(
        "/v1/families", headers=headers,
        json={"name": "可编辑家庭", "owner_nickname": "妈妈"},
    ).json()["data"]
    member = client.post(
        f"/v1/families/{family['id']}/members", headers=headers,
        json={"nickname": "宝宝"},
    ).json()["data"]

    deleted = client.delete(
        f"/v1/families/{family['id']}/members/{member['id']}", headers=headers
    )
    assert deleted.status_code == 200
    assert [item["nickname"] for item in deleted.json()["data"]["members"]] == ["妈妈"]

    protected = client.delete(
        f"/v1/families/{family['id']}/members/{family['members'][0]['id']}",
        headers=headers,
    )
    assert protected.status_code == 409
    assert protected.json()["error"]["code"] == "FAMILY_CREATOR_PROTECTED"


def test_validation_error_uses_standard_shape(client_and_repo) -> None:
    client, _ = client_and_repo
    response = client.post("/v1/auth/wechat", json={"code": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_phone_otp_is_single_use(client_and_repo) -> None:
    client, _ = client_and_repo
    requested = client.post("/v1/auth/otp/request", json={"phone": "13800138000"})
    assert requested.status_code == 200
    assert requested.json()["data"]["delivery_hint"] == "开发验证码：123456"

    first = client.post(
        "/v1/auth/otp/verify", json={"phone": "13800138000", "code": "123456"}
    )
    reused = client.post(
        "/v1/auth/otp/verify", json={"phone": "13800138000", "code": "123456"}
    )
    assert first.status_code == 200
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "OTP_INVALID"


def test_phone_login_restores_the_same_family_twenty_times(client_and_repo) -> None:
    client, _ = client_and_repo
    first = phone_login(client)
    family = client.post(
        "/v1/families",
        headers=auth(first["access_token"]),
        json={"name": "Web 家庭", "owner_nickname": "妈妈"},
    ).json()["data"]

    for _ in range(20):
        signed_in = phone_login(client)
        assert signed_in["family"]["id"] == family["id"]

    home = client.get("/v1/home", headers=auth(signed_in["access_token"]))
    assert home.status_code == 200
    assert home.json()["data"]["family"]["name"] == "Web 家庭"
    assert home.json()["data"]["family"]["member_labels"] == ["妈妈"]

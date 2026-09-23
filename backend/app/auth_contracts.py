from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WechatLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class RequestOtpRequest(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")


class VerifyOtpRequest(RequestOtpRequest):
    code: str = Field(pattern=r"^\d{6}$")


class OtpChallengeData(BaseModel):
    expires_in: int
    resend_after: int
    delivery_hint: str | None = None


class FamilyMemberData(BaseModel):
    id: UUID
    nickname: str
    character_profile: dict
    voice_consent: bool
    created_at: datetime
    updated_at: datetime


class FamilyData(BaseModel):
    id: UUID
    owner_user_id: UUID
    name: str
    members: list[FamilyMemberData]
    created_at: datetime
    updated_at: datetime


class AuthData(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: int
    user_id: UUID
    family: FamilyData | None


class SessionData(BaseModel):
    user_id: UUID
    family: FamilyData | None


class CreateFamilyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    owner_nickname: str = Field(min_length=1, max_length=24)


class RenameFamilyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class MemberRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)

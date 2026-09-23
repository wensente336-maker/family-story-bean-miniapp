from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth_contracts import (
    AuthData,
    CreateFamilyRequest,
    FamilyData,
    FamilyMemberData,
    MemberRequest,
    OtpChallengeData,
    RequestOtpRequest,
    RenameFamilyRequest,
    SessionData,
    WechatLoginRequest,
    VerifyOtpRequest,
)
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .repositories import FamilyRepository, PostgresFamilyRepository
from .security import InvalidTokenError, decode_access_token, hash_openid, hash_phone, issue_access_token
from .otp import (
    OtpDeliveryUnavailableError,
    OtpInvalidError,
    OtpRateLimitedError,
    RedisOtpService,
)
from .wechat import WechatCodeExchange, WechatLoginError


router = APIRouter(prefix="/v1", tags=["identity-and-family"])
bearer = HTTPBearer(auto_error=False)


def get_repository() -> FamilyRepository:
    return PostgresFamilyRepository(get_settings().database_url)


def get_wechat_exchange() -> WechatCodeExchange:
    return WechatCodeExchange(get_settings())


def get_otp_service() -> RedisOtpService:
    return RedisOtpService(get_settings())


def api_error(code: str, message: str, status_code: int, **details):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": False, "details": details},
    )


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    repository: FamilyRepository = Depends(get_repository),
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        api_error("AUTH_REQUIRED", "请先登录", status.HTTP_401_UNAUTHORIZED)
    settings = get_settings()
    try:
        claims = decode_access_token(credentials.credentials, settings.auth_signing_key)
    except InvalidTokenError:
        api_error("AUTH_INVALID", "登录已失效，请重新登录", status.HTTP_401_UNAUTHORIZED)
    if repository.get_user(claims.user_id) is None:
        api_error("AUTH_INVALID", "登录用户不存在", status.HTTP_401_UNAUTHORIZED)
    return claims.user_id


@router.post("/auth/wechat", response_model=ApiResponse[AuthData])
def wechat_login(
    body: WechatLoginRequest,
    request: Request,
    repository: FamilyRepository = Depends(get_repository),
    exchange: WechatCodeExchange = Depends(get_wechat_exchange),
):
    settings = get_settings()
    try:
        identity = exchange.exchange(body.code)
    except (WechatLoginError, ValueError):
        api_error("WECHAT_LOGIN_FAILED", "微信登录失败，请重试", status.HTTP_401_UNAUTHORIZED)
    user = repository.upsert_user(hash_openid(identity.openid, settings.auth_signing_key))
    family = repository.get_family_for_user(user["id"])
    token, expires_at = issue_access_token(
        user["id"], settings.auth_signing_key, settings.access_token_ttl_seconds
    )
    return ApiResponse(
        data=AuthData(
            access_token=token,
            expires_at=expires_at,
            user_id=user["id"],
            family=FamilyData.model_validate(family) if family else None,
        ),
        meta=meta_for(request),
    )


@router.post("/auth/otp/request", response_model=ApiResponse[OtpChallengeData])
def request_web_otp(
    body: RequestOtpRequest,
    request: Request,
    otp_service: RedisOtpService = Depends(get_otp_service),
):
    settings = get_settings()
    phone_digest = hash_phone(body.phone, settings.auth_signing_key)
    try:
        challenge = otp_service.request(phone_digest)
    except OtpRateLimitedError:
        api_error("OTP_RATE_LIMITED", "验证码请求过于频繁，请稍后再试", status.HTTP_429_TOO_MANY_REQUESTS)
    except OtpDeliveryUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "OTP_DELIVERY_UNAVAILABLE",
                "message": "短信服务尚未配置",
                "retryable": True,
                "details": {},
            },
        )
    return ApiResponse(data=OtpChallengeData(**challenge.__dict__), meta=meta_for(request))


@router.post("/auth/otp/verify", response_model=ApiResponse[AuthData])
def verify_web_otp(
    body: VerifyOtpRequest,
    request: Request,
    repository: FamilyRepository = Depends(get_repository),
    otp_service: RedisOtpService = Depends(get_otp_service),
):
    settings = get_settings()
    phone_digest = hash_phone(body.phone, settings.auth_signing_key)
    try:
        otp_service.verify(phone_digest, body.code)
    except OtpInvalidError:
        api_error("OTP_INVALID", "验证码错误或已失效", status.HTTP_401_UNAUTHORIZED)
    user = repository.upsert_phone_user(phone_digest)
    family = repository.get_family_for_user(user["id"])
    token, expires_at = issue_access_token(
        user["id"], settings.auth_signing_key, settings.access_token_ttl_seconds
    )
    return ApiResponse(
        data=AuthData(
            access_token=token,
            expires_at=expires_at,
            user_id=user["id"],
            family=FamilyData.model_validate(family) if family else None,
        ),
        meta=meta_for(request),
    )


@router.get("/session", response_model=ApiResponse[SessionData])
def restore_session(
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    family = repository.get_family_for_user(user_id)
    return ApiResponse(
        data=SessionData(
            user_id=user_id,
            family=FamilyData.model_validate(family) if family else None,
        ),
        meta=meta_for(request),
    )


@router.post(
    "/families", response_model=ApiResponse[FamilyData], status_code=status.HTTP_201_CREATED
)
def create_family(
    body: CreateFamilyRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    if repository.get_family_for_user(user_id):
        api_error("FAMILY_ALREADY_EXISTS", "当前用户已经创建家庭", status.HTTP_409_CONFLICT)
    family = repository.create_family(user_id, body.name.strip(), body.owner_nickname.strip())
    return ApiResponse(data=FamilyData.model_validate(family), meta=meta_for(request))


@router.get("/families/{family_id}", response_model=ApiResponse[FamilyData])
def get_family(
    family_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    family = repository.get_family(user_id, family_id)
    if family is None:
        api_error("FAMILY_NOT_FOUND", "家庭不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=FamilyData.model_validate(family), meta=meta_for(request))


@router.patch("/families/{family_id}", response_model=ApiResponse[FamilyData])
def rename_family(
    family_id: UUID,
    body: RenameFamilyRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    family = repository.rename_family(user_id, family_id, body.name.strip())
    if family is None:
        api_error("FAMILY_NOT_FOUND", "家庭不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=FamilyData.model_validate(family), meta=meta_for(request))


@router.post(
    "/families/{family_id}/members",
    response_model=ApiResponse[FamilyMemberData],
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    family_id: UUID,
    body: MemberRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    member = repository.add_member(user_id, family_id, body.nickname.strip())
    if member is None:
        api_error("FAMILY_NOT_FOUND", "家庭不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=FamilyMemberData.model_validate(member), meta=meta_for(request))


@router.patch(
    "/families/{family_id}/members/{member_id}",
    response_model=ApiResponse[FamilyMemberData],
)
def rename_member(
    family_id: UUID,
    member_id: UUID,
    body: MemberRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    member = repository.rename_member(user_id, family_id, member_id, body.nickname.strip())
    if member is None:
        api_error("MEMBER_NOT_FOUND", "家庭成员不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=FamilyMemberData.model_validate(member), meta=meta_for(request))


@router.delete(
    "/families/{family_id}/members/{member_id}",
    response_model=ApiResponse[FamilyData],
)
def delete_member(
    family_id: UUID,
    member_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
):
    family = repository.get_family(user_id, family_id)
    if family is None:
        api_error("FAMILY_NOT_FOUND", "家庭不存在或无权访问", status.HTTP_404_NOT_FOUND)
    if family["members"] and family["members"][0]["id"] == member_id:
        api_error("FAMILY_CREATOR_PROTECTED", "家庭创建者不能删除", status.HTTP_409_CONFLICT)
    updated = repository.delete_member(user_id, family_id, member_id)
    if updated is None:
        api_error("MEMBER_NOT_FOUND", "家庭成员不存在或无权访问", status.HTTP_404_NOT_FOUND)
    return ApiResponse(data=FamilyData.model_validate(updated), meta=meta_for(request))

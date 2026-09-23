from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .moment_contracts import MomentData, MomentListData, UpdateMomentRequest
from .moment_discovery import MomentDiscoveryService
from .moment_repository import MomentRepository, PostgresMomentRepository


router = APIRouter(prefix="/v1", tags=["moments"])


def get_moment_repository() -> MomentRepository:
    return PostgresMomentRepository(get_settings().database_url)


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def not_found():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "MOMENT_NOT_FOUND", "message": "高光不存在或无权访问", "retryable": False, "details": {}},
    )


@router.get("/recordings/{recording_id}/moments", response_model=ApiResponse[MomentListData])
def list_moments(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: MomentRepository = Depends(get_moment_repository),
):
    moments = repository.list_for_user(user_id, recording_id)
    if moments is None:
        not_found()
    return ApiResponse(
        data=MomentListData(recording_id=recording_id, moments=[MomentData.model_validate(item) for item in moments]),
        meta=meta_for(request),
    )


@router.post("/recordings/{recording_id}/moments/rebuild", response_model=ApiResponse[MomentListData])
def rebuild_moments(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: MomentRepository = Depends(get_moment_repository),
):
    if repository.list_for_user(user_id, recording_id) is None:
        not_found()
    MomentDiscoveryService(repository, get_settings().pipeline_version).process(recording_id)
    moments = repository.list_for_user(user_id, recording_id) or []
    return ApiResponse(
        data=MomentListData(recording_id=recording_id, moments=[MomentData.model_validate(item) for item in moments]),
        meta=meta_for(request),
    )


@router.get("/moments/{moment_id}", response_model=ApiResponse[MomentData])
def get_moment(
    moment_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: MomentRepository = Depends(get_moment_repository),
):
    moment = repository.get_for_user(user_id, moment_id)
    if moment is None:
        not_found()
    return ApiResponse(data=MomentData.model_validate(moment), meta=meta_for(request))


@router.patch("/moments/{moment_id}", response_model=ApiResponse[MomentData])
def update_moment(
    moment_id: UUID, body: UpdateMomentRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: MomentRepository = Depends(get_moment_repository),
):
    moment = repository.update_for_user(
        user_id, moment_id, body.selection_state, body.start_ms, body.end_ms
    )
    if moment is None:
        not_found()
    return ApiResponse(data=MomentData.model_validate(moment), meta=meta_for(request))

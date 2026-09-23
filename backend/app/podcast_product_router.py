from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .podcast_contracts import (
    CreatePodcastCommentRequest, DeletePodcastCoverData, PodcastCommentData,
    PodcastCommentPageData, PodcastProductData, PodcastReactionData,
    UpdatePodcastCommentRequest, UpdatePodcastProductRequest,
    DeletePodcastProductRequest, PodcastTrashActionData,
)
from .podcast_cover import CoverValidationError, PodcastCoverProcessor, SoundPostcardCoverProcessor
from .podcast_product_repository import (
    PodcastProductRepository, PostgresPodcastProductRepository,
)
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix="/v1", tags=["podcast-product"])


def get_podcast_product_repository() -> PodcastProductRepository:
    return PostgresPodcastProductRepository(get_settings().database_url)


def get_product_storage() -> LocalObjectStorage:
    return LocalObjectStorage(get_settings())


def get_cover_processor() -> PodcastCoverProcessor:
    return SoundPostcardCoverProcessor()


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


def product_not_found():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "PODCAST_PRODUCT_NOT_FOUND", "message": "播客成品不存在或尚未完成", "retryable": False, "details": {}},
    )


def hydrate_cover(product: dict, request: Request, storage: LocalObjectStorage) -> dict:
    cover = product.get("cover")
    if not cover:
        return product
    recording_id = product["recording_id"]
    token, _ = storage.issue_playback_token(recording_id, cover["object_key"], "image/webp")
    thumb_token, _ = storage.issue_playback_token(
        recording_id, cover["thumbnail_object_key"], "image/webp"
    )
    base = str(request.base_url).rstrip("/")
    product["cover"] = {
        "id": cover["id"], "url": f"{base}/v1/playback/{token}",
        "thumbnail_url": f"{base}/v1/playback/{thumb_token}",
        "media_type": "image/webp", "width": cover["width"], "height": cover["height"],
        "sha256": cover["sha256"],
        "aspect_ratio": cover.get("aspect_ratio", "1:1"),
        "layout_version": cover.get("layout_version", 1),
        "focal_x": float(cover.get("focal_x", .5)),
        "focal_y": float(cover.get("focal_y", .5)),
    }
    return product


@router.get(
    "/recordings/{recording_id}/podcast-product",
    response_model=ApiResponse[PodcastProductData],
)
def get_podcast_product(
    recording_id: UUID, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
):
    product = repository.get_by_recording(user_id, recording_id)
    if product is None:
        product_not_found()
    return ApiResponse(data=PodcastProductData.model_validate(hydrate_cover(product, request, storage)), meta=meta_for(request))


@router.patch(
    "/recordings/{recording_id}/podcast-product",
    response_model=ApiResponse[PodcastProductData],
)
def update_podcast_product(
    recording_id: UUID, body: UpdatePodcastProductRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
):
    product = repository.update(user_id, recording_id, body.title, body.description, body.tags)
    if product is None:
        product_not_found()
    return ApiResponse(data=PodcastProductData.model_validate(hydrate_cover(product, request, storage)), meta=meta_for(request))


@router.post(
    "/recordings/{recording_id}/podcast-product/cover",
    response_model=ApiResponse[PodcastProductData],
)
async def upload_podcast_cover(
    recording_id: UUID, request: Request,
    focal_x: float = Query(default=0.5, ge=0, le=1),
    focal_y: float = Query(default=0.5, ge=0, le=1),
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
    processor: PodcastCoverProcessor = Depends(get_cover_processor),
):
    content = await request.body()
    try:
        processed = processor.process(
            content, request.headers.get("content-type", "").split(";", 1)[0], focal_x, focal_y
        )
    except CoverValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "PODCAST_COVER_INVALID", "message": str(exc), "retryable": False, "details": {}},
        ) from exc
    asset_id = uuid4()
    base_key = f"recordings/{recording_id}/podcast-covers/{asset_id}"
    main_key, thumb_key = f"{base_key}/cover.webp", f"{base_key}/thumbnail.webp"
    main_path, thumb_path = storage.path_for(main_key), storage.path_for(thumb_key)
    main_path.parent.mkdir(parents=True, exist_ok=True)
    main_path.write_bytes(processed.main)
    thumb_path.write_bytes(processed.thumbnail)
    saved = repository.save_cover(user_id, recording_id, {
        "object_key": main_key, "thumbnail_object_key": thumb_key,
        "media_type": processed.media_type, "width": processed.width,
        "height": processed.height, "byte_size": len(content), "sha256": processed.sha256,
        "aspect_ratio": "3:4", "layout_version": 2,
        "focal_x": focal_x, "focal_y": focal_y,
    })
    if saved is None:
        storage.delete(main_key); storage.delete(thumb_key); product_not_found()
    product, old_keys = saved
    for key in old_keys:
        storage.delete(key)
    return ApiResponse(data=PodcastProductData.model_validate(hydrate_cover(product, request, storage)), meta=meta_for(request))


@router.delete(
    "/recordings/{recording_id}/podcast-product/cover",
    response_model=ApiResponse[DeletePodcastCoverData],
)
def delete_podcast_cover(
    recording_id: UUID, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
):
    keys = repository.delete_cover(user_id, recording_id)
    if keys is None:
        product_not_found()
    for key in keys:
        storage.delete(key)
    return ApiResponse(data=DeletePodcastCoverData(deleted=bool(keys)), meta=meta_for(request))


@router.get("/podcast-products", response_model=ApiResponse[list[PodcastProductData]])
def list_podcast_products(
    request: Request, tag: str | None = Query(default=None, max_length=30),
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
):
    products = [hydrate_cover(item, request, storage) for item in repository.list_by_tag(user_id, tag)]
    return ApiResponse(data=[PodcastProductData.model_validate(item) for item in products], meta=meta_for(request))


@router.get("/podcast-products/trash", response_model=ApiResponse[list[PodcastProductData]])
def list_podcast_trash(
    request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
    storage: LocalObjectStorage = Depends(get_product_storage),
):
    products = [hydrate_cover(item, request, storage) for item in repository.list_trash(user_id)]
    return ApiResponse(data=[PodcastProductData.model_validate(item) for item in products], meta=meta_for(request))


@router.delete("/recordings/{recording_id}/podcast-product", response_model=ApiResponse[PodcastTrashActionData])
def trash_podcast_product(
    recording_id: UUID, body: DeletePodcastProductRequest, request: Request,
    user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
):
    result = repository.set_deleted(user_id, recording_id, True)
    if result is None:
        product_not_found()
    return ApiResponse(data=PodcastTrashActionData.model_validate(result), meta=meta_for(request))


@router.post("/recordings/{recording_id}/podcast-product/restore", response_model=ApiResponse[PodcastTrashActionData])
def restore_podcast_product(
    recording_id: UUID, request: Request, user_id: UUID = Depends(current_user_id),
    repository: PodcastProductRepository = Depends(get_podcast_product_repository),
):
    result = repository.set_deleted(user_id, recording_id, False)
    if result is None:
        product_not_found()
    return ApiResponse(data=PodcastTrashActionData.model_validate(result), meta=meta_for(request))


@router.post("/podcast-products/{version_id}/like", response_model=ApiResponse[PodcastReactionData])
def like_podcast_product(version_id: UUID, request: Request, user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.set_like(user_id, version_id, True)
    if not result:
        product_not_found()
    return ApiResponse(data=PodcastReactionData.model_validate(result), meta=meta_for(request))


@router.delete("/podcast-products/{version_id}/like", response_model=ApiResponse[PodcastReactionData])
def unlike_podcast_product(version_id: UUID, request: Request, user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.set_like(user_id, version_id, False)
    if not result:
        product_not_found()
    return ApiResponse(data=PodcastReactionData.model_validate(result), meta=meta_for(request))


@router.get("/podcast-products/{version_id}/comments", response_model=ApiResponse[PodcastCommentPageData])
def list_podcast_comments(version_id: UUID, request: Request, cursor: UUID | None = Query(None), limit: int = Query(20, ge=1, le=50), user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.list_comments(user_id, version_id, cursor, limit)
    if result is None:
        product_not_found()
    return ApiResponse(data=PodcastCommentPageData.model_validate(result), meta=meta_for(request))


@router.post("/podcast-products/{version_id}/comments", response_model=ApiResponse[PodcastCommentData])
def create_podcast_comment(version_id: UUID, body: CreatePodcastCommentRequest, request: Request, user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.create_comment(user_id, version_id, body.body)
    if not result:
        product_not_found()
    return ApiResponse(data=PodcastCommentData.model_validate(result), meta=meta_for(request))


@router.patch("/podcast-comments/{comment_id}", response_model=ApiResponse[PodcastCommentData])
def update_podcast_comment(comment_id: UUID, body: UpdatePodcastCommentRequest, request: Request, user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.update_comment(user_id, comment_id, body.body)
    if not result:
        product_not_found()
    return ApiResponse(data=PodcastCommentData.model_validate(result), meta=meta_for(request))


@router.delete("/podcast-comments/{comment_id}")
def delete_podcast_comment(comment_id: UUID, request: Request, user_id: UUID = Depends(current_user_id), repository: PodcastProductRepository = Depends(get_podcast_product_repository)):
    result = repository.delete_comment(user_id, comment_id)
    if not result:
        product_not_found()
    return ApiResponse(data={"id": result["id"], "deleted": True}, meta=meta_for(request))

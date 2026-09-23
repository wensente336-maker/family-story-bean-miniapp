from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .comic_router import router as comic_router
from .podcast_router import router as podcast_router
from .podcast_material_router import router as podcast_material_router
from .podcast_plan_router import router as podcast_plan_router
from .podcast_render_router import router as podcast_render_router
from .podcast_product_router import router as podcast_product_router
from .podcast_share_router import router as podcast_share_router
from .podcast_release_router import router as podcast_release_router
from .contracts import ApiMeta, ApiResponse, HomeData, JobData, MomentSummary, ProcessingSummary
from .mock_data import build_home_data, build_job_data
from .auth_router import current_user_id, get_repository, router as auth_router
from .recording_router import get_recording_repository, router as recording_router
from .job_router import get_job_repository, router as job_router
from .job_repository import JobRepository
from .moment_repository import MomentRepository
from .moment_router import get_moment_repository, router as moment_router
from .repositories import FamilyRepository, RecordingRepository
from .transcript_router import router as transcript_router
from .lifecycle_router import router as lifecycle_router
from .storybook_router import router as storybook_router
from .highlight_router import router as highlight_router


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="家庭故事豆 MVP 的 API 契约与 Mock 联调服务。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
app.include_router(auth_router)
app.include_router(recording_router)
app.include_router(job_router)
app.include_router(transcript_router)
app.include_router(moment_router)
app.include_router(comic_router)
app.include_router(podcast_router)
app.include_router(podcast_material_router)
app.include_router(podcast_plan_router)
app.include_router(podcast_render_router)
app.include_router(podcast_product_router)
app.include_router(podcast_share_router)
app.include_router(podcast_release_router)
app.include_router(lifecycle_router)
app.include_router(storybook_router)
app.include_router(highlight_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, _exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务暂时不可用",
                "retryable": True,
                "details": {},
            },
            "meta": {"request_id": request_id, "timestamp": datetime.now(UTC).isoformat()},
        },
    )


def error_response(request: Request, status_code: int, error: dict):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": error,
            "meta": {"request_id": request_id, "timestamp": datetime.now(UTC).isoformat()},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return error_response(
        request,
        exc.status_code,
        {
            "code": detail.get("code", "HTTP_ERROR"),
            "message": detail.get("message", str(exc.detail)),
            "retryable": detail.get("retryable", False),
            "details": detail.get("details", {}),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception(request: Request, exc: RequestValidationError):
    fields = []
    for error in exc.errors():
        item = {key: value for key, value in error.items() if key != "ctx"}
        if error.get("ctx"):
            item["ctx"] = {
                key: str(value) for key, value in error["ctx"].items()
            }
        fields.append(item)
    return error_response(
        request,
        422,
        {
            "code": "VALIDATION_ERROR",
            "message": "请求参数不符合要求",
            "retryable": False,
            "details": {"fields": fields},
        },
    )


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id, timestamp=datetime.now(UTC))


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.app_env}


@app.get(
    "/v1/mock/home",
    response_model=ApiResponse[HomeData],
    tags=["mock"],
)
def mock_home(request: Request):
    return ApiResponse(data=build_home_data(), meta=meta_for(request))


@app.get(
    "/v1/home",
    response_model=ApiResponse[HomeData],
    tags=["web"],
    summary="Web 首页聚合数据",
)
def web_home(
    request: Request,
    user_id=Depends(current_user_id),
    repository: FamilyRepository = Depends(get_repository),
    recording_repository: RecordingRepository = Depends(get_recording_repository),
    job_repository: JobRepository = Depends(get_job_repository),
    moment_repository: MomentRepository = Depends(get_moment_repository),
):
    family = repository.get_family_for_user(user_id)
    if family is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "FAMILY_NOT_FOUND",
                "message": "请先创建家庭",
                "retryable": False,
                "details": {},
            },
        )
    latest = recording_repository.latest_recording(user_id)
    latest_job = job_repository.latest_for_user(user_id)
    processing = None
    if latest:
        active = latest_job if latest_job and latest_job["recording_id"] == latest["id"] else None
        display_stage = active["stage"] if active else latest["status"]
        status_text = {
            "UPLOADING": ("等待上传完成", 20),
            "UPLOADED": ("音频已安全保存", 100),
            "CREATED": ("等待进入处理队列", 0),
            "PREPROCESSING": ("正在读取和整理音频", 25),
            "TRANSCRIBING": ("正在识别家人的对话", 50),
            "ANALYZING": ("正在发现值得留下的时刻", 75),
            "READY_FOR_SELECTION": ("故事高光已经准备好", 100),
            "FAILED": ("处理遇到问题，可查看详情并重试", 0),
        }.get(str(display_stage), ("录音已创建", 0))
        processing = ProcessingSummary(
            recording_id=latest["id"],
            job_id=active["id"] if active else latest["id"],
            title=latest["title"],
            detail=status_text[0],
            stage=display_stage,
            progress=active["progress"] if active else status_text[1],
        )
    moment_rows = moment_repository.list_for_user(user_id, latest["id"]) if latest else []
    moment_summaries = []
    for index, moment in enumerate(moment_rows or []):
        board = moment["storyboard"]
        moment_summaries.append(MomentSummary(
            id=moment["id"], recording_id=moment["recording_id"],
            theme=moment.get("theme") or board["story_type"],
            duration_ms=moment["end_ms"] - moment["start_ms"], title=moment["title"],
            quote=board.get("highlight_quote") or board["setup"],
            color="coral" if index % 2 else "sun",
        ))
    home = HomeData(
        family={
            "id": family["id"],
            "name": family["name"],
            "member_labels": [member["nickname"] for member in family["members"]],
        },
        processing=processing,
        moments=moment_summaries,
    )
    return ApiResponse(data=home, meta=meta_for(request))


@app.get(
    "/v1/mock/jobs/{job_id}",
    response_model=ApiResponse[JobData],
    tags=["mock"],
)
def mock_job(job_id: str, request: Request):
    job = build_job_data()
    if job_id != str(job.id):
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": "任务不存在",
                    "retryable": False,
                    "details": {"job_id": job_id},
                },
                "meta": meta_for(request).model_dump(mode="json"),
            },
        )
    return ApiResponse(data=job, meta=meta_for(request))

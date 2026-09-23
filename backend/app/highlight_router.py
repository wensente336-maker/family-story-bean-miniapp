from datetime import UTC, datetime
from html import escape
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse

from .auth_router import current_user_id
from .config import get_settings
from .contracts import ApiMeta, ApiResponse
from .highlight_audio import HighlightAudioClipper, HighlightAudioError
from .highlight_contracts import (
    CreateHighlightCommentRequest, CreateHighlightShareRequest, HighlightCommentData,
    HighlightCommentPageData, HighlightReactionData, HighlightShareData,
    HighlightTrashActionData, HighlightWorkData, PublicHighlightData,
    UpdateHighlightCommentRequest, UpdateHighlightWorkRequest,
)
from .highlight_repository import HighlightRepository, PostgresHighlightRepository
from .podcast_cover import CoverValidationError, SoundPostcardCoverProcessor
from .upload_storage import LocalObjectStorage


router = APIRouter(prefix='/v1', tags=['highlight-works'])


def get_highlight_repository() -> HighlightRepository:
    return PostgresHighlightRepository(get_settings().database_url)


def get_highlight_storage() -> LocalObjectStorage:
    return LocalObjectStorage(get_settings())


def meta_for(request: Request) -> ApiMeta:
    return ApiMeta(request_id=request.state.request_id,timestamp=datetime.now(UTC))


def not_found(message='高光作品不存在或无权访问'):
    raise HTTPException(status_code=404,detail={'code':'HIGHLIGHT_NOT_FOUND','message':message,'retryable':False,'details':{}})


def prepare_audio(work: dict, repository: HighlightRepository, storage: LocalObjectStorage) -> dict:
    if work['audio_status'] != 'PENDING':
        return work
    source_key = work.get('source_object_key')
    if not source_key:
        repository.set_audio(work['id'],'UNAVAILABLE',code='ORIGINAL_AUDIO_PURGED')
        return {**work,'audio_status':'UNAVAILABLE'}
    key=f"recordings/{work['recording_id']}/highlights/{work['id']}/clip.mp3"
    try:
        HighlightAudioClipper().clip(storage.path_for(source_key),storage.path_for(key),work['start_ms'],work['end_ms'])
        repository.set_audio(work['id'],'READY',key=key)
        return {**work,'audio_status':'READY','audio_object_key':key}
    except FileNotFoundError:
        repository.set_audio(work['id'],'UNAVAILABLE',code='ORIGINAL_AUDIO_PURGED')
        return {**work,'audio_status':'UNAVAILABLE'}
    except HighlightAudioError:
        repository.set_audio(work['id'],'FAILED',code='AUDIO_CLIP_FAILED')
        return {**work,'audio_status':'FAILED'}


def hydrate(work: dict, request: Request, storage: LocalObjectStorage) -> dict:
    base=str(request.base_url).rstrip('/')
    work={**work,'audio_url':None}
    if work['audio_status']=='READY' and work.get('audio_object_key'):
        token,_=storage.issue_playback_token(work['recording_id'],work['audio_object_key'],'audio/mpeg')
        work['audio_url']=f'{base}/v1/playback/{token}'
    cover=work.get('cover')
    if cover:
        token,_=storage.issue_playback_token(work['recording_id'],cover['object_key'],'image/webp')
        thumb,_=storage.issue_playback_token(work['recording_id'],cover['thumbnail_object_key'],'image/webp')
        work['cover']={'id':cover['id'],'url':f'{base}/v1/playback/{token}','thumbnail_url':f'{base}/v1/playback/{thumb}',
                       'width':cover['width'],'height':cover['height'],'sha256':cover['sha256'],
                       'aspect_ratio':cover.get('aspect_ratio','1:1'),'layout_version':cover.get('layout_version',1),
                       'focal_x':float(cover.get('focal_x',.5)),'focal_y':float(cover.get('focal_y',.5))}
    return work


def data(work,request,storage):
    return HighlightWorkData.model_validate(hydrate(work,request,storage))


@router.post('/moments/{moment_id}/highlight-work',response_model=ApiResponse[HighlightWorkData])
def save_highlight(moment_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),
                   repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    work=repository.save_from_moment(user_id,moment_id)
    if not work:not_found('请先把这个时刻标记为保留')
    work=prepare_audio(work,repository,storage)
    fresh=repository.get_for_user(user_id,work['id']) or work
    return ApiResponse(data=data(fresh,request,storage),meta=meta_for(request))


@router.get('/highlight-works',response_model=ApiResponse[list[HighlightWorkData]])
def list_highlights(request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    works=repository.list_for_user(user_id)
    # Complete migration-created clips on first access. Failures remain visible and retryable.
    for work in works:
        if work['audio_status']=='PENDING':
            prepare_audio(work,repository,storage)
    works=repository.list_for_user(user_id)
    return ApiResponse(data=[data(item,request,storage) for item in works],meta=meta_for(request))


@router.get('/highlight-works/trash',response_model=ApiResponse[list[HighlightWorkData]])
def list_highlight_trash(request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    return ApiResponse(data=[data(item,request,storage) for item in repository.list_for_user(user_id,True)],meta=meta_for(request))


@router.get('/highlight-works/{work_id}',response_model=ApiResponse[HighlightWorkData])
def get_highlight(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    work=repository.get_for_user(user_id,work_id)
    if not work:not_found()
    if work['audio_status'] in {'PENDING','FAILED'}:
        prepare_audio(work,repository,storage)
        work=repository.get_for_user(user_id,work_id) or work
    return ApiResponse(data=data(work,request,storage),meta=meta_for(request))


@router.patch('/highlight-works/{work_id}',response_model=ApiResponse[HighlightWorkData])
def update_highlight(work_id:UUID,body:UpdateHighlightWorkRequest,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    work=repository.update(user_id,work_id,body.title,body.quote)
    if not work:not_found()
    return ApiResponse(data=data(work,request,storage),meta=meta_for(request))


@router.post('/highlight-works/{work_id}/cover',response_model=ApiResponse[HighlightWorkData])
async def upload_highlight_cover(work_id:UUID,request:Request,focal_x:float=Query(.5,ge=0,le=1),focal_y:float=Query(.5,ge=0,le=1),
    user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    content=await request.body()
    try:processed=SoundPostcardCoverProcessor().process(content,request.headers.get('content-type','').split(';',1)[0],focal_x,focal_y)
    except CoverValidationError as exc:raise HTTPException(status_code=422,detail={'code':'HIGHLIGHT_COVER_INVALID','message':str(exc),'retryable':False,'details':{}}) from exc
    work=repository.get_for_user(user_id,work_id)
    if not work:not_found()
    asset=uuid4();base=f"recordings/{work['recording_id']}/highlights/{work_id}/covers/{asset}"
    main,thumb=f'{base}/cover.webp',f'{base}/thumbnail.webp'
    storage.path_for(main).parent.mkdir(parents=True,exist_ok=True);storage.path_for(main).write_bytes(processed.main);storage.path_for(thumb).write_bytes(processed.thumbnail)
    saved=repository.save_cover(user_id,work_id,{'object_key':main,'thumbnail_object_key':thumb,'width':processed.width,'height':processed.height,'byte_size':len(content),'sha256':processed.sha256,'aspect_ratio':'3:4','layout_version':2,'focal_x':focal_x,'focal_y':focal_y})
    if not saved:storage.delete(main);storage.delete(thumb);not_found()
    work,old=saved
    for key in old:storage.delete(key)
    return ApiResponse(data=data(work,request,storage),meta=meta_for(request))


@router.delete('/highlight-works/{work_id}/cover')
def delete_highlight_cover(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    keys=repository.delete_cover(user_id,work_id)
    if keys is None:not_found()
    for key in keys:storage.delete(key)
    return ApiResponse(data={'deleted':bool(keys)},meta=meta_for(request))


@router.delete('/highlight-works/{work_id}',response_model=ApiResponse[HighlightTrashActionData])
def trash_highlight(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.set_deleted(user_id,work_id,True)
    if not result:not_found()
    return ApiResponse(data=HighlightTrashActionData.model_validate(result),meta=meta_for(request))


@router.post('/highlight-works/{work_id}/restore',response_model=ApiResponse[HighlightTrashActionData])
def restore_highlight(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.set_deleted(user_id,work_id,False)
    if not result:not_found()
    return ApiResponse(data=HighlightTrashActionData.model_validate(result),meta=meta_for(request))


@router.post('/highlight-works/{work_id}/like',response_model=ApiResponse[HighlightReactionData])
def like_highlight(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.set_like(user_id,work_id,True)
    if not result:not_found()
    return ApiResponse(data=HighlightReactionData.model_validate(result),meta=meta_for(request))


@router.delete('/highlight-works/{work_id}/like',response_model=ApiResponse[HighlightReactionData])
def unlike_highlight(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.set_like(user_id,work_id,False)
    if not result:not_found()
    return ApiResponse(data=HighlightReactionData.model_validate(result),meta=meta_for(request))


@router.get('/highlight-works/{work_id}/comments',response_model=ApiResponse[HighlightCommentPageData])
def list_highlight_comments(work_id:UUID,request:Request,cursor:UUID|None=Query(None),limit:int=Query(20,ge=1,le=50),user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.list_comments(user_id,work_id,cursor,limit)
    if result is None:not_found()
    return ApiResponse(data=HighlightCommentPageData.model_validate(result),meta=meta_for(request))


@router.post('/highlight-works/{work_id}/comments',response_model=ApiResponse[HighlightCommentData])
def create_highlight_comment(work_id:UUID,body:CreateHighlightCommentRequest,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.create_comment(user_id,work_id,body.body)
    if not result:not_found()
    return ApiResponse(data=HighlightCommentData.model_validate(result),meta=meta_for(request))


@router.patch('/highlight-comments/{comment_id}',response_model=ApiResponse[HighlightCommentData])
def update_highlight_comment(comment_id:UUID,body:UpdateHighlightCommentRequest,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.update_comment(user_id,comment_id,body.body)
    if not result:not_found('评论不存在或无权编辑')
    return ApiResponse(data=HighlightCommentData.model_validate(result),meta=meta_for(request))


@router.delete('/highlight-comments/{comment_id}')
def delete_highlight_comment(comment_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    result=repository.delete_comment(user_id,comment_id)
    if not result:not_found('评论不存在或无权删除')
    return ApiResponse(data={'id':result['id'],'deleted':True},meta=meta_for(request))


def share_data(row,url=''):
    return HighlightShareData(id=row['id'],highlight_work_id=row['highlight_work_id'],title=row['title'],url=url,
      expires_at=row['expires_at'],revoked_at=row.get('revoked_at'),access_count=row.get('access_count',0),created_at=row['created_at'])


@router.post('/highlight-works/{work_id}/shares',response_model=ApiResponse[HighlightShareData])
def create_highlight_share(work_id:UUID,body:CreateHighlightShareRequest,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    row=repository.create_share(user_id,work_id,body.expires_in_hours)
    if not row:not_found('高光尚未准备好或家庭已关闭分享')
    url=f"{get_settings().public_web_base_url.rstrip('/')}/highlight-share/{row['token']}"
    return ApiResponse(data=share_data(row,url),meta=meta_for(request))


@router.get('/highlight-works/{work_id}/shares',response_model=ApiResponse[list[HighlightShareData]])
def list_highlight_shares(work_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    return ApiResponse(data=[share_data(row) for row in repository.list_shares(user_id,work_id)],meta=meta_for(request))


@router.delete('/highlight-shares/{share_id}',response_model=ApiResponse[HighlightShareData])
def revoke_highlight_share(share_id:UUID,request:Request,user_id:UUID=Depends(current_user_id),repository:HighlightRepository=Depends(get_highlight_repository)):
    row=repository.revoke_share(user_id,share_id)
    if not row:not_found('分享不存在或无权撤销')
    return ApiResponse(data=share_data(row),meta=meta_for(request))


@router.get('/public/highlight-shares/{token}',response_model=ApiResponse[PublicHighlightData])
def public_highlight(token:str,request:Request,repository:HighlightRepository=Depends(get_highlight_repository)):
    row=repository.resolve_share(token)
    if not row:not_found('分享已过期或被撤销')
    base=str(request.base_url).rstrip('/')
    return ApiResponse(data=PublicHighlightData(title=row['title'],quote=row['quote'],duration_ms=row['duration_ms'],
      audio_url=f'{base}/v1/public/highlight-shares/{token}/audio',cover_url=f'{base}/v1/public/highlight-shares/{token}/cover' if row.get('cover_object_key') else None,expires_at=row['expires_at']),meta=meta_for(request))


@router.get('/public/highlight-shares/{token}/audio')
def public_highlight_audio(token:str,repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    row=repository.resolve_share(token,False)
    if not row:not_found('分享音频已失效')
    path=storage.path_for(row['audio_object_key'])
    if not path.exists():not_found('分享音频不存在')
    return FileResponse(path,media_type='audio/mpeg',headers={'Cache-Control':'private, no-store'})


@router.get('/public/highlight-shares/{token}/cover')
def public_highlight_cover(token:str,repository:HighlightRepository=Depends(get_highlight_repository),storage:LocalObjectStorage=Depends(get_highlight_storage)):
    row=repository.resolve_share(token,False)
    if not row or not row.get('cover_object_key'):not_found('分享图片不存在')
    return FileResponse(storage.path_for(row['cover_object_key']),media_type='image/webp',headers={'Cache-Control':'private, no-store'})

import { ChangeEvent, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { ArrowLeft, Camera, Check, Heart, LoaderCircle, MessageCircle, Pause, Pencil, Play, Save, Share2, Trash2, Waves } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { HighlightSharePanel } from "../components/HighlightSharePanel";
import { PodcastDialog } from "../components/PodcastDialog";
import { PostcardComments } from "../components/PostcardComments";
import { deleteHighlightCover, getHighlightWork, likeHighlight, unlikeHighlight, updateHighlightWork, uploadHighlightCover, type HighlightWork } from "../services/highlightApi";

export function HighlightPage(){
  const{id=""}=useParams(),[params]=useSearchParams(),audio=useRef<HTMLAudioElement>(null),titleRef=useRef<HTMLInputElement>(null);
  const[work,setWork]=useState<HighlightWork|null>(null),[title,setTitle]=useState(""),[quote,setQuote]=useState(""),[playing,setPlaying]=useState(false),[progress,setProgress]=useState(0),[editing,setEditing]=useState(params.get("edit")==="1"),[sharing,setSharing]=useState(false),[comments,setComments]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  useEffect(()=>{let active=true;void getHighlightWork(id).then(value=>{if(active){setWork(value);setTitle(value.title);setQuote(value.quote)}}).catch(()=>active&&setError("声音明信片暂时无法读取。"));return()=>{active=false}},[id]);
  useEffect(()=>{if(editing&&work){titleRef.current?.focus();titleRef.current?.scrollIntoView({block:"center"})}},[editing,work?.id]);
  const togglePlay=async()=>{if(!audio.current||!work?.audio_url)return;if(playing){audio.current.pause();setPlaying(false);return}try{await audio.current.play();setPlaying(true)}catch{setError("这段声音暂时无法播放。")} };
  const upload=async(event:ChangeEvent<HTMLInputElement>)=>{const file=event.target.files?.[0];event.target.value="";if(!file||!work)return;if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>5*1024*1024){setError("请选择 5MB 以内的 JPG、PNG 或 WebP 图片。");return}setBusy(true);setError("");try{const next=await uploadHighlightCover(work.id,file);setWork(next);setNotice("竖版明信片封面已更新。") }catch{setError("图片上传失败，请重试。")}finally{setBusy(false)}};
  const save=async()=>{if(!work)return;setBusy(true);setError("");try{const next=await updateHighlightWork(work.id,{title,quote});setWork(next);setTitle(next.title);setQuote(next.quote);setEditing(false);setNotice("声音明信片已保存。") }catch{setError("保存失败，请重试。")}finally{setBusy(false)}};
  const removeCover=async()=>{if(!work)return;setBusy(true);try{await deleteHighlightCover(work.id);const next=await getHighlightWork(work.id);setWork(next);setNotice("封面图片已移除。")}catch{setError("图片移除失败。")}finally{setBusy(false)}};
  const toggleLike=async()=>{if(!work||busy)return;const previous=work;setWork({...work,liked_by_me:!work.liked_by_me,like_count:Math.max(0,work.like_count+(work.liked_by_me?-1:1))});setBusy(true);try{const result=work.liked_by_me?await unlikeHighlight(work.id):await likeHighlight(work.id);setWork(current=>current?{...current,liked_by_me:result.liked,like_count:result.like_count}:current)}catch{setWork(previous);setError("点赞未能保存，请重试。")}finally{setBusy(false)}};
  if(!work)return <div className="postcard-page"><section className="progress-loading">{error?<><p>{error}</p><Link to="/postcards">返回声音明信片</Link></>:<><LoaderCircle className="spin"/><p>正在打开声音明信片…</p></>}</section></div>;
  const image=work.cover?.url,legacy=Boolean(work.cover&&work.cover.layout_version<2);
  return <div className="postcard-page"><div className="postcard-topline"><Link className="progress-back" to="/postcards"><ArrowLeft size={17}/>返回声音明信片</Link><span>FAMILY SOUND POSTCARD</span></div>
    {error&&<p className="moment-review-error" role="alert">{error}</p>}{notice&&<p className="plan-notice" role="status"><Check size={15}/>{notice}</p>}
    <article className="sound-postcard">
      <div className="postcard-action-dock" aria-label="明信片互动">
        <button aria-label="分享声音明信片" onClick={()=>setSharing(true)}><Share2 size={19}/></button>
        <button className={work.liked_by_me?"active":""} aria-label={work.liked_by_me?"取消点赞":"点赞"} aria-pressed={work.liked_by_me} onClick={()=>void toggleLike()}><Heart size={19} fill={work.liked_by_me?"currentColor":"none"}/><span>{work.like_count||""}</span></button>
        <button aria-label="查看评论" onClick={()=>setComments(true)}><MessageCircle size={19}/><span>{work.comment_count||""}</span></button>
      </div>
      <div className={`postcard-image ${image?"has-image":""} ${legacy?"legacy-cover":""}`} style={image?{"--postcard-image":`url(${image})`} as CSSProperties:undefined}>
        <div className="postcard-image-backdrop"/>
        {!image&&<div className="postcard-placeholder"><Waves size={62}/><span>把这一刻装进声音里</span></div>}
        <button className="postcard-play" disabled={!work.audio_url} aria-label={playing?"暂停声音":"播放声音"} onClick={()=>void togglePlay()} style={{"--progress":`${progress*360}deg`} as CSSProperties}>{playing?<Pause size={28}/>:<Play size={28}/>}</button>
        {work.can_edit&&<label className="postcard-upload" aria-label={busy?"正在上传图片":"上传或更换封面图片"}><Camera size={17}/><span>{busy?"上传中":"换图"}</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={upload}/></label>}
        <span className="postcard-duration">原声 · {Math.max(1,Math.round(work.duration_ms/1000))} 秒</span>
      </div>
      <div className="postcard-message"><span>声音明信片</span><blockquote>“{work.quote}”</blockquote><footer><time>{new Date(work.created_at).toLocaleDateString("zh-CN",{year:"numeric",month:"long",day:"numeric"})}</time><button onClick={()=>setEditing(value=>!value)}><Pencil size={14}/>{editing?"收起编辑":"编辑文字"}</button></footer></div>
    </article>
    <audio ref={audio} src={work.audio_url||undefined} preload="metadata" onTimeUpdate={event=>{const target=event.currentTarget;setProgress(target.duration?target.currentTime/target.duration:0)}} onEnded={()=>{setPlaying(false);setProgress(0)}}/>
    {editing&&<section className="postcard-editor"><header><Pencil size={18}/><div><strong>编辑明信片文字</strong><small>不会覆盖逐字稿或播客内容</small></div></header><label>标题<input ref={titleRef} value={title} maxLength={120} onChange={event=>setTitle(event.target.value)}/></label><label>一句话<textarea value={quote} maxLength={500} onChange={event=>setQuote(event.target.value)}/></label><div>{work.cover&&<button className="danger-quiet" disabled={busy} onClick={()=>void removeCover()}><Trash2 size={14}/>移除图片</button>}<button className="primary-button" disabled={busy||!title.trim()||!quote.trim()} onClick={()=>void save()}><Save size={15}/>{busy?"正在保存…":"保存明信片"}</button></div></section>}
    {sharing&&<PodcastDialog title="分享声音明信片" onClose={()=>setSharing(false)}><HighlightSharePanel work={work}/></PodcastDialog>}
    {comments&&<PodcastDialog title={`评论 · ${work.comment_count}`} onClose={()=>setComments(false)}><PostcardComments workId={work.id} onCountChange={delta=>setWork(current=>current?{...current,comment_count:Math.max(0,current.comment_count+delta)}:current)}/></PodcastDialog>}
  </div>
}

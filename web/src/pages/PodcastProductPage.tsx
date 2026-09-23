import type { CSSProperties } from "react";
import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Camera, Check, Download, Heart, LoaderCircle, MessageCircle, MoreHorizontal, Pause, Pencil, Play, Save, Share2, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PodcastDialog } from "../components/PodcastDialog";
import { PodcastSharePanel } from "../components/PodcastSharePanel";
import { GramophoneComments } from "../components/GramophoneComments";
import { ApiClientError } from "../services/apiClient";
import { deletePodcastCover, getPodcastProduct, getPodcastRenderPlayback, getRecordingPodcastRenderJob, likePodcastProduct, unlikePodcastProduct, updatePodcastProduct, uploadPodcastCover, type PodcastProduct, type PodcastRenderPlayback } from "../services/podcastApi";

function clock(milliseconds=0){const seconds=Math.max(0,Math.round(milliseconds/1000));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}`}

export function PodcastProductPage(){
  const{id=""}=useParams(),navigate=useNavigate(),[params]=useSearchParams(),audio=useRef<HTMLAudioElement>(null),titleRef=useRef<HTMLInputElement>(null);
  const[product,setProduct]=useState<PodcastProduct|null>(null),[playback,setPlayback]=useState<PodcastRenderPlayback|null>(null),[playing,setPlaying]=useState(false),[progress,setProgress]=useState(0),[editing,setEditing]=useState(params.get("edit")==="1"),[sharing,setSharing]=useState(false),[comments,setComments]=useState(false),[menuOpen,setMenuOpen]=useState(false),[title,setTitle]=useState(""),[description,setDescription]=useState(""),[tags,setTags]=useState<string[]>([]),[customTag,setCustomTag]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const applyProduct=(next:PodcastProduct)=>{setProduct(next);setTitle(next.title);setDescription(next.description);setTags(next.tags.map(item=>item.name))};
  useEffect(()=>{let active=true;setError("");void getPodcastProduct(id).then(next=>{if(active)applyProduct(next)}).catch(reason=>active&&setError(reason instanceof ApiClientError?reason.message:"家庭留声机暂时无法读取。"));void getRecordingPodcastRenderJob(id).then(render=>getPodcastRenderPlayback(render.job.id)).then(value=>active&&setPlayback(value)).catch(()=>active&&setError("作品已读取，但播放地址暂时无法签发。"));return()=>{active=false}},[id]);
  useEffect(()=>{if(editing&&product){titleRef.current?.focus();titleRef.current?.scrollIntoView({block:"center"})}},[editing,product?.recording_id]);
  const togglePlay=async()=>{if(!audio.current||!playback)return;if(playing){audio.current.pause();setPlaying(false);return}try{await audio.current.play();setPlaying(true)}catch{setError("这段声音暂时无法播放。")}};
  const upload=async(event:ChangeEvent<HTMLInputElement>)=>{const file=event.target.files?.[0];event.target.value="";if(!file)return;if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>5*1024*1024){setError("请选择 5MB 以内的 JPG、PNG 或 WebP 图片。");return}setBusy(true);setError("");try{applyProduct(await uploadPodcastCover(id,file,.5,.42));setNotice("3:4 留声机封面已更新。")}catch{setError("封面上传失败，请重试。")}finally{setBusy(false)}};
  const removeCover=async()=>{setBusy(true);setError("");try{await deletePodcastCover(id);applyProduct(await getPodcastProduct(id));setNotice("已恢复默认黑胶留声机封面。")}catch{setError("封面移除失败，请重试。")}finally{setBusy(false)}};
  const toggleLike=async()=>{if(!product||busy)return;const previous=product;setProduct({...product,liked_by_me:!product.liked_by_me,like_count:Math.max(0,product.like_count+(product.liked_by_me?-1:1))});setBusy(true);try{const result=product.liked_by_me?await unlikePodcastProduct(product.podcast_version_id):await likePodcastProduct(product.podcast_version_id);setProduct(current=>current?{...current,liked_by_me:result.liked,like_count:result.like_count}:current)}catch{setProduct(previous);setError("点赞未能保存，请重试。")}finally{setBusy(false)}};
  const toggleTag=(name:string)=>setTags(current=>current.includes(name)?current.filter(item=>item!==name):current.length<5?[...current,name]:current);
  const addCustomTag=()=>{const next=customTag.trim();if(!next||tags.some(item=>item.toLowerCase()===next.toLowerCase())||tags.length>=5)return;setTags(current=>[...current,next]);setCustomTag("")};
  const save=async()=>{if(!title.trim())return;setBusy(true);setError("");try{const next=await updatePodcastProduct(id,{title:title.trim(),description:description.trim(),tags});applyProduct(next);setEditing(false);setNotice("家庭留声机已保存，音频未重新混音。")}catch(reason){setError(reason instanceof ApiClientError?reason.message:"作品信息保存失败。")}finally{setBusy(false)}};
  const systemTags=useMemo(()=>product?.available_tags.filter(item=>item.kind==="system")??[],[product]);
  if(!product)return <div className="gramophone-page"><section className="progress-loading">{error?<><AlertTriangle/><p>{error}</p><Link to="/podcasts">返回家庭留声机</Link></>:<><LoaderCircle className="spin"/><p>正在打开家庭留声机…</p></>}</section></div>;
  const customCover=product.cover?.url;
  const coverStyle=customCover?{"--gramophone-cover":`url(${customCover})`,"--gramophone-position":`${product.cover!.focal_x*100}% ${product.cover!.focal_y*100}%`} as CSSProperties:undefined;
  return <div className="gramophone-page">
    <div className="gramophone-topline"><button className="progress-back" onClick={()=>navigate("/podcasts")}><ArrowLeft size={17}/>返回家庭留声机</button><span>FAMILY GRAMOPHONE</span></div>
    {error&&<p className="moment-review-error" role="alert">{error}</p>}{notice&&<p className="plan-notice" role="status"><Check size={15}/>{notice}</p>}
    <article className={`family-gramophone ${customCover?"has-custom-cover":"has-vinyl-cover"}`} style={coverStyle}>
      <div className="gramophone-action-dock" aria-label="留声机互动">
        <button aria-label="分享家庭留声机" onClick={()=>setSharing(true)}><Share2 size={19}/></button>
        <button className={product.liked_by_me?"active":""} aria-label={product.liked_by_me?"取消点赞":"点赞"} aria-pressed={product.liked_by_me} onClick={()=>void toggleLike()}><Heart size={19} fill={product.liked_by_me?"currentColor":"none"}/><span>{product.like_count||""}</span></button>
        <button aria-label="查看评论" onClick={()=>setComments(true)}><MessageCircle size={19}/><span>{product.comment_count||""}</span></button>
      </div>
      <label className="gramophone-upload"><Camera size={17}/><span>{busy?"上传中":"更换封面"}</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={upload}/></label>
      <div className={`gramophone-cover ${customCover?"custom-cover":"vinyl-cover"} ${playing?"is-playing":""}`}>{!customCover&&<img src="/assets/family-vinyl-record.png" alt="复古黑胶唱片"/>}</div>
      <button className="gramophone-play" disabled={!playback} aria-label={playing?"暂停声音":"播放声音"} onClick={()=>void togglePlay()}>{playing?<Pause size={30}/>:<Play size={30}/>}</button>
      <div className="gramophone-content">
        <div className="gramophone-meta"><span>家庭留声机 · VOL. {String(product.version).padStart(2,"0")}</span><time>{clock(product.duration_ms)}</time></div>
        <h1>{product.title}</h1>
        <p>{product.description||"把家人的声音，留在一张会唱歌的唱片里。"}</p>
        {product.tags.length>0&&<div className="gramophone-tags">{product.tags.map(item=><span key={item.id}>#{item.name}</span>)}</div>}
        <div className="gramophone-footer"><span>{Math.round(progress*100)}% · {product.render_mode==="narrated"?"AI 解说与家人原声":"家庭原声精剪"}</span><div className="gramophone-more"><button aria-label="更多操作" aria-expanded={menuOpen} onClick={()=>setMenuOpen(value=>!value)}><MoreHorizontal size={19}/>更多</button>{menuOpen&&<div role="menu"><button onClick={()=>{setEditing(true);setMenuOpen(false)}}><Pencil size={15}/>编辑作品</button>{playback&&<a href={playback.download_url} download onClick={()=>setMenuOpen(false)}><Download size={15}/>下载 MP3</a>}</div>}</div></div>
      </div>
    </article>
    <audio ref={audio} src={playback?.url} preload="metadata" onTimeUpdate={event=>{const target=event.currentTarget;setProgress(target.duration?target.currentTime/target.duration:0)}} onEnded={()=>{setPlaying(false);setProgress(0)}}/>
    {editing&&<section className="gramophone-editor"><header><Pencil size={18}/><div><strong>编辑家庭留声机</strong><small>修改主题内容和标签不会重新混音</small></div></header><label>标题<input ref={titleRef} value={title} maxLength={120} onChange={event=>setTitle(event.target.value)}/></label><label>声音主题内容<textarea value={description} maxLength={500} onChange={event=>setDescription(event.target.value)}/></label><div className="product-tags">{systemTags.map(item=><button key={item.id} className={tags.includes(item.name)?"selected":""} onClick={()=>toggleTag(item.name)}><Check size={12}/>{item.name}</button>)}</div><div className="custom-tag"><input value={customTag} maxLength={30} placeholder="自定义标签" onChange={event=>setCustomTag(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();addCustomTag()}}}/><button onClick={addCustomTag} disabled={tags.length>=5}>添加</button></div><div className="selected-tags">{tags.map(item=><button key={item} onClick={()=>toggleTag(item)}>#{item} ×</button>)}</div><footer>{product.cover&&<button className="danger-quiet" disabled={busy} onClick={()=>void removeCover()}><Trash2 size={14}/>恢复默认封面</button>}<button className="secondary-button" onClick={()=>setEditing(false)}>取消</button><button className="primary-button" disabled={busy||!title.trim()} onClick={()=>void save()}><Save size={15}/>{busy?"正在保存…":"保存作品"}</button></footer></section>}
    {sharing&&<PodcastDialog title="分享家庭留声机" onClose={()=>setSharing(false)}><PodcastSharePanel product={product}/></PodcastDialog>}
    {comments&&<PodcastDialog title={`评论 · ${product.comment_count}`} onClose={()=>setComments(false)}><GramophoneComments versionId={product.podcast_version_id} onCountChange={delta=>setProduct(current=>current?{...current,comment_count:Math.max(0,current.comment_count+delta)}:current)}/></PodcastDialog>}
  </div>
}

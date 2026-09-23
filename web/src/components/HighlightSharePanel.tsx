import { useEffect, useState } from "react";
import { Check, Clock3, Copy, ExternalLink, LoaderCircle, Share2, XCircle } from "lucide-react";
import { createHighlightShare, listHighlightShares, revokeHighlightShare, type HighlightShare, type HighlightWork } from "../services/highlightApi";
import { shareOrCopy } from "../utils/share";

export function HighlightSharePanel({ work }: { work: HighlightWork }) {
  const [hours,setHours]=useState(24),[shares,setShares]=useState<HighlightShare[]>([]),[url,setUrl]=useState(""),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[notice,setNotice]=useState(""),[error,setError]=useState("");
  useEffect(()=>{let active=true; setLoading(true); void listHighlightShares(work.id).then(value=>active&&setShares(value)).catch(()=>active&&setError("分享记录读取失败。" )).finally(()=>active&&setLoading(false));return()=>{active=false}},[work.id]);
  const create=async()=>{setBusy(true);setError("");try{const share=await createHighlightShare(work.id,hours);setShares(v=>[share,...v]);setUrl(share.url);try{await navigator.clipboard.writeText(share.url);setNotice("链接已创建并复制。")}catch{setNotice("链接已创建。")}}catch{setError("分享链接创建失败。") }finally{setBusy(false)}};
  const revoke=async(id:string)=>{setBusy(true);try{const result=await revokeHighlightShare(id);setShares(v=>v.map(item=>item.id===id?result:item));setNotice("分享链接已撤销。") }catch{setError("撤销失败。") }finally{setBusy(false)}};
  const copy=async()=>{try{await navigator.clipboard.writeText(url);setNotice("链接已复制。") }catch{setError("复制失败，请手动复制。")}};
  return <section className="product-sharing podcast-share-panel"><div className="product-section-title"><Share2 size={20}/><div><strong>限时私密分享</strong><small>只分享这张高光的图片、文案和片段音频</small></div></div>
    {error&&<p className="moment-review-error" role="alert">{error}</p>}{notice&&<p className="plan-notice" role="status"><Check size={15}/>{notice}</p>}
    <div className="share-create-row"><label>有效期<select value={hours} onChange={e=>setHours(Number(e.target.value))}><option value={24}>24 小时</option><option value={72}>3 天</option><option value={168}>7 天</option></select></label><button className="primary-button" disabled={busy||loading||work.audio_status!=="READY"||!work.share_allowed} onClick={()=>void create()}>{busy?<LoaderCircle className="spin" size={15}/>:<Share2 size={15}/>}创建限时链接</button></div>
    {work.audio_status!=="READY"&&<p className="share-unavailable">片段音频准备完成后才可分享。</p>}
    {!work.share_allowed&&<p className="share-unavailable">这段原声被标记为仅家庭可见，不能创建外部分享链接。</p>}
    {url&&<div className="share-ready"><input readOnly value={url} onFocus={e=>e.target.select()}/><button onClick={()=>void copy()}><Copy size={14}/>复制</button><button onClick={()=>void shareOrCopy({title:work.title,text:work.quote,url})}><ExternalLink size={14}/>系统分享</button><a href={url} target="_blank" rel="noreferrer"><ExternalLink size={14}/>预览</a></div>}
    <div className="share-history">{loading?<p>正在读取分享记录…</p>:shares.length?shares.map(share=>{const inactive=Boolean(share.revoked_at)||new Date(share.expires_at)<=new Date();return <article key={share.id} className={inactive?"inactive":""}><div><strong>{share.revoked_at?"已撤销":inactive?"已过期":"分享中"}</strong><small><Clock3 size={12}/>{new Date(share.expires_at).toLocaleString("zh-CN")} 失效 · 访问 {share.access_count} 次</small></div>{!inactive&&<button disabled={busy} onClick={()=>void revoke(share.id)}><XCircle size={14}/>撤销</button>}</article>}):<p>还没有创建过分享链接。</p>}</div>
  </section>;
}

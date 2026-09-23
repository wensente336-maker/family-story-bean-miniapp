import { FormEvent, useEffect, useState } from "react";
import { LoaderCircle, MessageCircle, Pencil, Send, Trash2, X } from "lucide-react";
import { createPodcastComment, deletePodcastComment, listPodcastComments, updatePodcastComment, type PodcastComment } from "../services/podcastApi";

export function GramophoneComments({versionId,onCountChange}:{versionId:string;onCountChange:(delta:number)=>void}){
  const[items,setItems]=useState<PodcastComment[]>([]),[cursor,setCursor]=useState<string|null>(null),[text,setText]=useState(""),[editing,setEditing]=useState<PodcastComment|null>(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const load=async(next?:string)=>{setLoading(true);setError("");try{const page=await listPodcastComments(versionId,next);setItems(current=>next?[...current,...page.items]:page.items);setCursor(page.next_cursor)}catch{setError("评论暂时无法读取，请稍后重试。")}finally{setLoading(false)}};
  useEffect(()=>{void load()},[versionId]);
  const submit=async(event:FormEvent)=>{event.preventDefault();const body=text.trim();if(!body||busy)return;setBusy(true);setError("");try{if(editing){const saved=await updatePodcastComment(editing.id,body);setItems(value=>value.map(item=>item.id===saved.id?saved:item));setEditing(null)}else{const saved=await createPodcastComment(versionId,body);setItems(value=>[saved,...value]);onCountChange(1)}setText("")}catch{setError("评论未能保存，请重试。")}finally{setBusy(false)}};
  const remove=async(comment:PodcastComment)=>{setBusy(true);try{await deletePodcastComment(comment.id);setItems(value=>value.filter(item=>item.id!==comment.id));onCountChange(-1);if(editing?.id===comment.id){setEditing(null);setText("")}}catch{setError("评论未能删除，请重试。")}finally{setBusy(false)}};
  return <section className="postcard-comments"><header><MessageCircle size={18}/><div><strong>家庭评论</strong><small>只有同一家庭的登录成员可以查看和留言</small></div></header>
    <form onSubmit={submit}><textarea aria-label={editing?"编辑评论":"写下评论"} maxLength={500} placeholder="写下一句想一起记住的话…" value={text} onChange={event=>setText(event.target.value)}/><div><span>{text.length}/500</span>{editing&&<button type="button" className="comment-cancel" onClick={()=>{setEditing(null);setText("")}}><X size={14}/>取消编辑</button>}<button className="comment-send" disabled={busy||!text.trim()}>{busy?<LoaderCircle className="spin" size={15}/>:<Send size={15}/>}发布</button></div></form>
    {error&&<p className="moment-review-error" role="alert">{error}</p>}
    <div className="comment-list">{loading&&!items.length?<p>正在打开评论…</p>:items.length?items.map(comment=><article key={comment.id}><div className="comment-avatar">{comment.author_name.slice(0,1)}</div><div><header><strong>{comment.author_name}</strong><time>{new Date(comment.created_at).toLocaleString("zh-CN")}</time></header><p>{comment.body}</p>{(comment.can_edit||comment.can_delete)&&<footer>{comment.can_edit&&<button onClick={()=>{setEditing(comment);setText(comment.body)}}><Pencil size={13}/>编辑</button>}{comment.can_delete&&<button onClick={()=>void remove(comment)}><Trash2 size={13}/>删除</button>}</footer>}</div></article>):<p>还没有评论，留下第一句话吧。</p>}</div>
    {cursor&&<button className="comment-more" disabled={loading} onClick={()=>void load(cursor)}>{loading?"正在加载…":"查看更多评论"}</button>}
  </section>
}

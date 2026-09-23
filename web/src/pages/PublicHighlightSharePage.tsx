import { useEffect, useState } from "react";
import { Headphones, LoaderCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import { getPublicHighlight, type PublicHighlight } from "../services/highlightApi";

export function PublicHighlightSharePage(){const{token=""}=useParams();const[data,setData]=useState<PublicHighlight|null>(null),[error,setError]=useState("");useEffect(()=>{void getPublicHighlight(token).then(setData).catch(()=>setError("这份家庭高光已过期或被撤销。"))},[token]);if(!data)return <main className="public-highlight-page"><section>{error?<><Headphones/><h1>链接已失效</h1><p>{error}</p></>:<><LoaderCircle className="spin"/><p>正在打开这份声音记忆…</p></>}</section></main>;return <main className="public-highlight-page"><article><div className={`public-highlight-cover ${data.cover_url?"has-image":""}`} style={data.cover_url?{backgroundImage:`url(${data.cover_url})`}:undefined}>{!data.cover_url&&<Headphones size={54}/>}</div><span>家庭故事豆 · 限时私密分享</span><h1>{data.title}</h1><blockquote>“{data.quote}”</blockquote><audio controls preload="metadata" src={data.audio_url}/><small>有效至 {new Date(data.expires_at).toLocaleString("zh-CN")}</small></article></main>}

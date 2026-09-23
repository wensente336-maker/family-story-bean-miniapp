import { Clock3, Headphones, LoaderCircle, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getPublicShare, type PublicShare } from "../services/lifecycleApi";

export function PublicSharePage() {
  const { token = "" } = useParams();
  const [share, setShare] = useState<PublicShare | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getPublicShare(token).then(setShare).catch(() => setError("这个分享链接已经过期或被家人撤销。")); }, [token]);
  if (!share) return <div className="public-share-page"><section className="public-share-loading">{error ? <><ShieldCheck /><h1>链接已失效</h1><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在打开这份家庭记忆…</p></>}</section></div>;
  return <div className="public-share-page"><header><span>家庭故事豆 · 限时私密分享</span><h1>{share.title}</h1><p><Clock3 size={14} />有效至 {new Date(share.expires_at).toLocaleString("zh-CN")}</p></header>
    {share.creation_type === "PODCAST" ? <section className="public-podcast"><Headphones size={56} /><strong>一段来自家里的声音</strong>{share.media_url && <audio controls src={share.media_url} />}</section> : <section className="public-comic-grid">{share.panels.map((panel) => {
      const composite = panel.asset_url.includes("four-panel");
      return <article key={panel.panel_index}><div style={{ backgroundImage: `url(${panel.asset_url})`, backgroundSize: composite ? "200% 200%" : "cover", backgroundPosition: composite ? `${panel.crop_x ? 100 : 0}% ${panel.crop_y ? 100 : 0}%` : "center" }}>{panel.dialogue && <blockquote>{panel.dialogue}</blockquote>}</div><p>{panel.narration}</p></article>;
    })}</section>}
    <footer><ShieldCheck size={14} />链接可由家庭创建者随时撤销，页面不展示原始录音或家庭成员资料。</footer>
  </div>;
}

import { AlertTriangle, ArrowLeft, Copy, Download, Headphones, Image as ImageIcon, LoaderCircle, Share2, ShieldCheck, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ImmersiveBookReader } from "../components/ImmersiveBookReader";
import { SoundStoryDirector } from "../components/SoundStoryDirector";
import { env } from "../config/env";
import { storybookTitle } from "../features/storybook/bookManifest";
import { getComic, regenerateComicPanel, type Comic, type ComicPanel } from "../services/comicApi";
import { createShare, getPrivacySettings } from "../services/lifecycleApi";
import { createOrRefreshStorybook, type Storybook, type StoryPlan } from "../services/storybookApi";

function panelStyle(panel: ComicPanel) {
  const composite = panel.asset_url.includes("four-panel");
  return {
    backgroundImage: `url(${panel.asset_url})`,
    backgroundSize: composite ? "200% 200%" : "cover",
    backgroundPosition: composite
      ? `${panel.crop_x ? 100 : 0}% ${panel.crop_y ? 100 : 0}%`
      : "center",
  };
}

export function ComicPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [comic, setComic] = useState<Comic | null>(null);
  const [storybook, setStorybook] = useState<Storybook | null>(null);
  const [storyPlan, setStoryPlan] = useState<StoryPlan | null>(null);
  const [regenerating, setRegenerating] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareHours, setShareHours] = useState(24);
  const handlePlanChange = useCallback((plan: StoryPlan) => setStoryPlan(plan), []);

  useEffect(() => {
    getComic(id).then(async (value) => {
      setComic(value);
      if (!env.features.comicCreation) return;
      try {
        setStorybook(await createOrRefreshStorybook(value.id));
      } catch {
        setStorybook(null);
      }
    }).catch(() => setError("漫画暂时无法读取，请稍后重试。"));
    getPrivacySettings().then((settings) => setShareHours(settings.share_default_hours)).catch(() => undefined);
  }, [id]);

  const regenerate = async (panelIndex: number) => {
    setRegenerating(panelIndex); setError("");
    try {
      const updated = await regenerateComicPanel(id, panelIndex);
      setComic(updated);
      try {
        setStorybook(await createOrRefreshStorybook(updated.id));
      } catch {
        setStorybook(null);
        setError("漫画已重画，但电子书版本暂未同步，请刷新页面重试。");
      }
    } catch {
      setError("这一格没有生成成功，请重试。");
    } finally {
      setRegenerating(null);
    }
  };

  const download = async () => {
    if (!comic) return;
    setExporting(true); setError("");
    try {
      const blob = await renderLongComic(comic);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${comic.title.replace(/[\\/:*?"<>|]/g, "-")}.png`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("长图导出失败，请稍后重试。");
    } finally {
      setExporting(false);
    }
  };

  const share = async () => {
    setSharing(true); setError("");
    try {
      const result = await createShare(id, shareHours); setShareUrl(result.url);
      await navigator.clipboard?.writeText(result.url);
    } catch { setError("分享链接创建失败，请检查隐私设置。"); }
    finally { setSharing(false); }
  };

  if (!comic) return <div className="comic-page"><section className="progress-loading">{error ? <><AlertTriangle /><p>{error}</p></> : <><LoaderCircle className="spin" /><p>正在装订家庭漫画…</p></>}</section></div>;

  const bible = comic.metadata.visual_bible;
  const storyTitle = storybookTitle(comic);
  return <div className="comic-page">
    <button className="progress-back" onClick={() => navigate(-1)}><ArrowLeft size={17} />返回高光</button>
    <header className="comic-header"><span className="section-kicker">{env.features.comicCreation ? "FAMILY STORYBOOK" : "ARCHIVED FAMILY COMIC"}</span><h1>{storyTitle}</h1><p>{env.features.comicCreation ? "从家人真实声音出发，先编排故事，再让画面、解说和原声沿同一时间线发生。" : "这是已经生成的历史家庭漫画。新版创作已转向声音播客，原作品仍可查看、导出和私密分享。"}</p></header>
    {bible && <section className="character-bible"><ShieldCheck size={19} /><div><strong>人物一致性已锁定</strong><small>{bible.characters.map((item) => item.display_name).join("、")} · {bible.palette.join(" / ")}</small></div><span>v{comic.version}</span></section>}
    {error && <p className="comic-error"><AlertTriangle size={15} />{error}</p>}
    {!env.features.comicCreation && <section className="character-bible"><ShieldCheck size={19} /><div><strong>历史作品只读保留</strong><small>不会继续生成、重画或同步新的有声绘本版本。</small></div><span>归档</span></section>}
    {!env.features.comicCreation && <section className="comic-grid" aria-label="历史家庭漫画">{comic.panels.map((panel) => <article className="comic-panel" key={panel.id}><div className="comic-art" style={panelStyle(panel)}><span className="panel-number">{panel.panel_index}</span>{panel.dialogue && <blockquote>“{panel.dialogue}”</blockquote>}</div><div className="comic-caption"><p>{panel.narration}</p><span>{panel.source_segment_id ? "原话可追溯" : "AI 创作旁白"} · v{panel.version}</span></div></article>)}</section>}
    {env.features.comicCreation && storybook && <SoundStoryDirector storybook={storybook} onPlanChange={handlePlanChange} />}
    {env.features.comicCreation && storybook && storyPlan?.status === "CONFIRMED"
      ? <ImmersiveBookReader key={`${storybook.id}:${storyPlan.revision}`} comic={comic} storybook={storybook} regenerating={regenerating} onRegenerate={regenerate} />
      : env.features.comicCreation ? <section className="storybook-awaiting-confirmation"><Headphones size={23} /><div><strong>有声绘本等待声音故事线确认</strong><small>确认人物原声后，系统才会生成同步的漫画场景、解说与混合音轨。</small></div></section> : null}
    <section className="comic-export"><ImageIcon size={22} /><div><strong>{env.features.comicCreation ? "当前四格仅作为人物风格参考" : "历史家庭漫画已安全保留"}</strong><small>{env.features.comicCreation ? "声音故事线确认后，最终绘本会按导演分场重新生成；这里仍可导出或分享旧版参考图。" : "你仍然可以导出长图或创建私密分享链接，但系统不会修改原有画面。"}</small>{shareUrl && <span className="creation-share-url"><input readOnly value={shareUrl} /><button onClick={() => void navigator.clipboard?.writeText(shareUrl)}><Copy size={14} />复制</button></span>}</div><span className="creation-export-actions"><button disabled={sharing} onClick={() => void share()}>{sharing ? <LoaderCircle className="spin" size={16} /> : <Share2 size={16} />}{env.features.comicCreation ? "分享参考图" : "分享历史漫画"}</button><button className="primary-button" disabled={exporting} onClick={() => void download()}>{exporting ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}{exporting ? "正在导出" : env.features.comicCreation ? "导出参考图" : "导出长图"}</button></span></section>
    <p className="comic-ai-note"><Sparkles size={13} />{env.features.comicCreation ? "家庭原声是创作事实源；AI 解说与画面必须能够回溯到声音故事线。" : "历史漫画数据保持不变；新的家庭故事将以声音播客形式生成。"}</p>
  </div>;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

function wrapText(context: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines = 3) {
  const characters = [...text];
  let line = "";
  let row = 0;
  for (const character of characters) {
    const next = line + character;
    if (context.measureText(next).width > maxWidth && line) {
      if (row === maxLines - 1) {
        let clipped = line;
        while (clipped && context.measureText(`${clipped}…`).width > maxWidth) clipped = clipped.slice(0, -1);
        context.fillText(`${clipped}…`, x, y + row * lineHeight);
        return;
      }
      context.fillText(line, x, y + row * lineHeight);
      row += 1; line = character;
    } else line = next;
  }
  if (line && row < maxLines) context.fillText(line, x, y + row * lineHeight);
}

async function renderLongComic(comic: Comic): Promise<Blob> {
  const width = 1080;
  const artHeight = 610;
  const captionHeight = 150;
  const margin = 54;
  const headerHeight = 255;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = headerHeight + comic.panels.length * (artHeight + captionHeight + 26) + 80;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("canvas unavailable");
  context.fillStyle = "#f5f0e8"; context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#173b3d"; context.font = "700 46px 'PingFang SC', sans-serif";
  wrapText(context, comic.title, margin, 78, width - margin * 2, 55, 3);
  context.fillStyle = "#b65d49"; context.font = "700 20px 'PingFang SC', sans-serif";
  context.fillText("家庭故事豆 · 四格家庭漫画", margin, 215);
  let y = headerHeight;
  for (const panel of comic.panels) {
    const image = await loadImage(panel.asset_url);
    const composite = panel.asset_url.includes("four-panel");
    const sourceWidth = composite ? image.naturalWidth / 2 : image.naturalWidth;
    const sourceHeight = composite ? image.naturalHeight / 2 : image.naturalHeight;
    const sourceX = composite ? panel.crop_x * sourceWidth : 0;
    const sourceY = composite ? panel.crop_y * sourceHeight : 0;
    context.save();
    roundedRect(context, margin, y, width - margin * 2, artHeight, 26);
    context.clip();
    context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, margin, y, width - margin * 2, artHeight);
    context.restore();
    context.fillStyle = "#173b3d"; context.beginPath(); context.arc(margin + 40, y + 40, 25, 0, Math.PI * 2); context.fill();
    context.fillStyle = "white"; context.font = "700 23px sans-serif"; context.textAlign = "center"; context.fillText(String(panel.panel_index), margin + 40, y + 48); context.textAlign = "left";
    if (panel.dialogue) {
      context.fillStyle = "rgba(255,253,248,.94)";
      roundedRect(context, margin + 36, y + 72, width - margin * 2 - 72, 104, 20); context.fill();
      context.fillStyle = "#173b3d"; context.font = "600 25px 'PingFang SC', sans-serif";
      wrapText(context, `“${panel.dialogue}”`, margin + 61, y + 112, width - margin * 2 - 122, 34, 2);
    }
    context.fillStyle = "#fffdf8"; context.fillRect(margin, y + artHeight, width - margin * 2, captionHeight);
    context.fillStyle = "#445b58"; context.font = "500 25px 'PingFang SC', sans-serif";
    wrapText(context, panel.narration, margin + 28, y + artHeight + 50, width - margin * 2 - 56, 34, 2);
    context.fillStyle = "#a56452"; context.font = "600 17px 'PingFang SC', sans-serif";
    context.fillText(panel.source_segment_id ? "原话可追溯" : "AI 创作旁白", margin + 28, y + artHeight + 123);
    y += artHeight + captionHeight + 26;
  }
  return await new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("export failed")), "image/png"));
}

function roundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

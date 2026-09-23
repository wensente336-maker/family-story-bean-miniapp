import {
  BookOpen, ChevronLeft, ChevronRight, FastForward, Headphones,
  Music2, Pause, Play, RefreshCw, RotateCcw, Sparkles, Volume2, VolumeX,
} from "lucide-react";
import { PageFlip, type PageFlipEvent } from "page-flip";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPrototypeBookManifest } from "../features/storybook/bookManifest";
import type { Comic, ComicPanel } from "../services/comicApi";
import {
  createStorybookExperienceSession,
  type Storybook,
  type StorybookExperienceSession,
} from "../services/storybookApi";

type ReaderPage = {
  index: number;
  type: "cover" | "story" | "ending";
  title: string;
  narration: string;
  assetUrl?: string;
  panel?: ComicPanel;
};

type AudioState =
  | "等待开启"
  | "正在准备故事"
  | "故事解说"
  | "家庭原声"
  | "原声暂不可用"
  | "已暂停";

function panelBackground(panel: ComicPanel) {
  const composite = panel.asset_url.includes("four-panel");
  return {
    backgroundImage: `url(${panel.asset_url})`,
    backgroundSize: composite ? "200% 200%" : "cover",
    backgroundPosition: composite
      ? `${panel.crop_x ? 100 : 0}% ${panel.crop_y ? 100 : 0}%`
      : "center",
  };
}

function pageBackground(page: ReaderPage) {
  if (page.assetUrl) return {
    backgroundImage: `url(${page.assetUrl})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
  };
  return page.panel ? panelBackground(page.panel) : undefined;
}

function chineseVoice() {
  return window.speechSynthesis?.getVoices().find((voice) =>
    voice.lang.toLowerCase().startsWith("zh")
  );
}

export function ImmersiveBookReader({
  comic,
  storybook,
  regenerating,
  onRegenerate,
}: {
  comic: Comic;
  storybook: Storybook | null;
  regenerating: number | null;
  onRegenerate: (panelIndex: number) => Promise<void> | void;
}) {
  const manifest = useMemo(
    () => storybook?.manifest ?? createPrototypeBookManifest(comic),
    [comic, storybook],
  );
  const basePages = useMemo<ReaderPage[]>(() => manifest.pages.map((page) => ({
    index: page.index,
    type: page.type,
    title: page.title,
    narration: page.narration,
    panel: page.panelIndex === null
      ? undefined
      : comic.panels.find((panel) => panel.panel_index === page.panelIndex),
  })), [comic.panels, manifest.pages]);

  const bookRef = useRef<HTMLDivElement>(null);
  const pageFlipRef = useRef<PageFlip | null>(null);
  const recordingRef = useRef<HTMLAudioElement>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const musicGainRef = useRef<GainNode | null>(null);
  const ambientNodesRef = useRef<OscillatorNode[]>([]);
  const autoTimerRef = useRef<number | null>(null);
  const currentPageRef = useRef(0);
  const reducedMotionRef = useRef(false);
  const destroyTimerRef = useRef<number | null>(null);
  const soundStartedRef = useRef(false);
  const mutedRef = useRef(false);
  const autoPlayRef = useRef(false);
  const experienceRef = useRef<StorybookExperienceSession | null>(null);
  const timelineDrivenFlipRef = useRef(false);
  const timelineFlipReleaseRef = useRef<number | null>(null);

  const [currentPage, setCurrentPage] = useState(0);
  const [soundStarted, setSoundStarted] = useState(false);
  const [muted, setMuted] = useState(false);
  const [musicOn, setMusicOn] = useState(true);
  const [autoPlay, setAutoPlay] = useState(false);
  const [audioState, setAudioState] = useState<AudioState>("等待开启");
  const [experience, setExperience] = useState<StorybookExperienceSession | null>(null);
  const [currentLine, setCurrentLine] = useState("");
  const [reducedMotion, setReducedMotion] = useState(() =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
  );
  const pages = useMemo<ReaderPage[]>(() => {
    if (!experience) return basePages;
    return experience.scenes.map((scene) => ({
      index: scene.pageIndex,
      type: scene.type,
      title: scene.title,
      narration: scene.narration,
      assetUrl: scene.assetUrl ?? undefined,
      panel: comic.panels.find((panel) => (
        panel.panel_index === (scene.fallbackPanelIndex ?? ((scene.pageIndex % 4) || 4))
      )),
    }));
  }, [basePages, comic.panels, experience]);

  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
  }, [reducedMotion]);

  const clearAutoTimer = useCallback(() => {
    if (autoTimerRef.current !== null) window.clearTimeout(autoTimerRef.current);
    autoTimerRef.current = null;
  }, []);

  const stopPageAudio = useCallback(() => {
    clearAutoTimer();
    window.speechSynthesis?.cancel();
    recordingRef.current?.pause();
  }, [clearAutoTimer]);

  useEffect(() => {
    experienceRef.current = null;
    setExperience(null);
    setCurrentLine("");
  }, [storybook?.id, storybook?.currentVersion]);

  const ensureExperience = useCallback(async () => {
    if (!storybook) return null;
    const current = experienceRef.current;
    if (
      current
      && current.version === storybook.currentVersion
      && current.expiresAt > Math.floor(Date.now() / 1000) + 15
    ) return current;
    setAudioState("正在准备故事");
    try {
      const next = await createStorybookExperienceSession(storybook.id);
      experienceRef.current = next;
      setExperience(next);
      if (musicGainRef.current) musicGainRef.current.gain.value = 0;
      if (!soundStartedRef.current) setAudioState("等待开启");
      return next;
    } catch {
      setAudioState("原声暂不可用");
      return null;
    }
  }, [storybook]);

  useEffect(() => {
    if (storybook) void ensureExperience();
  }, [ensureExperience, storybook]);

  const queueAutoFlip = useCallback(() => {
    if (!autoPlayRef.current || currentPageRef.current >= pages.length - 1) return;
    autoTimerRef.current = window.setTimeout(() => {
      const book = pageFlipRef.current;
      if (!book) return;
      if (reducedMotionRef.current) book.turnToNextPage();
      else book.flipNext("bottom");
    }, 1100);
  }, [pages.length]);

  const speakFallback = useCallback((text: string, onEnd = queueAutoFlip) => {
    if (!soundStartedRef.current || mutedRef.current || !window.speechSynthesis) {
      onEnd();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = 0.9;
    utterance.pitch = 1.02;
    utterance.volume = 0.92;
    const voice = chineseVoice();
    if (voice) utterance.voice = voice;
    utterance.onstart = () => { setAudioState("故事解说"); setCurrentLine(text); };
    utterance.onend = onEnd;
    utterance.onerror = onEnd;
    window.speechSynthesis.speak(utterance);
  }, [queueAutoFlip]);

  const playPage = useCallback(async (pageIndex: number) => {
    stopPageAudio();
    if (!soundStartedRef.current || mutedRef.current) return;
    const page = pages[pageIndex];
    if (!page) return;
    const recording = recordingRef.current;
    if (storybook && recording) {
      const session = await ensureExperience();
      if (currentPageRef.current !== pageIndex) return;
      const scene = session?.scenes.find((item) => item.pageIndex === page.index);
      if (session && scene) {
        if (recording.src !== session.url) recording.src = session.url;
        recording.currentTime = scene.audioStartMs / 1000;
        recording.volume = 0.95;
        setAudioState("故事解说");
        setCurrentLine(scene.narration);
        void recording.play().catch(() => setAudioState("原声暂不可用"));
        return;
      }
    }
    speakFallback(page.narration);
  }, [ensureExperience, pages, speakFallback, stopPageAudio, storybook]);

  const syncExperienceTimeline = useCallback(() => {
    const session = experienceRef.current;
    const recording = recordingRef.current;
    if (!session || !recording) return;
    const positionMs = Math.round(recording.currentTime * 1000);
    const cue = session.cues.find((item) => (
      positionMs >= item.startMs && positionMs < item.endMs
    ));
    if (cue) {
      setAudioState(cue.kind === "original" ? "家庭原声" : "故事解说");
      setCurrentLine(cue.text);
    }
    const scene = session.scenes.find((item) => (
      positionMs >= item.audioStartMs && positionMs < item.audioEndMs
    ));
    if (
      !scene
      || scene.pageIndex === currentPageRef.current
      || timelineDrivenFlipRef.current
    ) return;
    const book = pageFlipRef.current;
    if (!book) return;
    timelineDrivenFlipRef.current = true;
    if (timelineFlipReleaseRef.current !== null) {
      window.clearTimeout(timelineFlipReleaseRef.current);
    }
    timelineFlipReleaseRef.current = window.setTimeout(() => {
      timelineDrivenFlipRef.current = false;
      timelineFlipReleaseRef.current = null;
    }, reducedMotionRef.current ? 240 : 920);
    if (reducedMotionRef.current) book.turnToPage(scene.pageIndex);
    else book.flip(scene.pageIndex, "bottom");
  }, []);

  const playFlipSound = useCallback(() => {
    const context = contextRef.current;
    if (!context || mutedRef.current) return;
    const duration = 0.22;
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      const envelope = Math.sin(Math.PI * index / samples.length) * (1 - index / samples.length);
      samples[index] = (Math.random() * 2 - 1) * envelope * 0.24;
    }
    const source = context.createBufferSource();
    const filter = context.createBiquadFilter();
    const gain = context.createGain();
    source.buffer = buffer;
    filter.type = "bandpass";
    filter.frequency.value = 1450;
    filter.Q.value = 0.7;
    gain.gain.value = 0.22;
    source.connect(filter).connect(gain).connect(context.destination);
    source.start();
  }, []);

  const startAmbientMusic = useCallback((context: AudioContext) => {
    if (ambientNodesRef.current.length) return;
    const master = context.createGain();
    const filter = context.createBiquadFilter();
    master.gain.value = 0.026;
    filter.type = "lowpass";
    filter.frequency.value = 620;
    master.connect(filter).connect(context.destination);
    [130.81, 164.81, 196].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = index === 1 ? "sine" : "triangle";
      oscillator.frequency.value = frequency;
      gain.gain.value = index === 1 ? 0.24 : 0.16;
      oscillator.connect(gain).connect(master);
      oscillator.start();
      ambientNodesRef.current.push(oscillator);
    });
    musicGainRef.current = master;
  }, []);

  const startSound = useCallback(async () => {
    let context = contextRef.current;
    if (!context) {
      context = new AudioContext();
      contextRef.current = context;
      startAmbientMusic(context);
    }
    await context.resume();
    soundStartedRef.current = true;
    mutedRef.current = false;
    setSoundStarted(true);
    setMuted(false);
    void playPage(currentPageRef.current);
  }, [playPage, startAmbientMusic]);

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    if (musicGainRef.current) {
      musicGainRef.current.gain.value = next || !musicOn || Boolean(experienceRef.current) ? 0 : 0.026;
    }
    if (recordingRef.current) recordingRef.current.volume = next ? 0 : 0.95;
    if (next) {
      stopPageAudio();
      setAudioState("已暂停");
    } else {
      void playPage(currentPageRef.current);
    }
  }, [musicOn, playPage, stopPageAudio]);

  useEffect(() => {
    if (musicGainRef.current) {
      musicGainRef.current.gain.value = musicOn && !muted && !experience ? 0.026 : 0;
    }
  }, [experience, musicOn, muted]);

  useEffect(() => {
    autoPlayRef.current = autoPlay;
    if (!experience && autoPlay && soundStarted) void playPage(currentPageRef.current);
    else if ((!autoPlay || experience) && autoTimerRef.current !== null) clearAutoTimer();
  }, [autoPlay, clearAutoTimer, experience, playPage, soundStarted]);

  useEffect(() => {
    const root = bookRef.current;
    if (!root) return;
    if (destroyTimerRef.current !== null) window.clearTimeout(destroyTimerRef.current);
    if (!pageFlipRef.current) {
      const flipBook = new PageFlip(root, {
        width: 510,
        height: 650,
        size: "stretch",
        minWidth: 280,
        maxWidth: 510,
        minHeight: 390,
        maxHeight: 650,
        drawShadow: true,
        flippingTime: reducedMotionRef.current ? 120 : 760,
        usePortrait: true,
        autoSize: true,
        maxShadowOpacity: 0.34,
        showCover: true,
        mobileScrollSupport: true,
        clickEventForward: true,
        useMouseEvents: true,
        showPageCorners: !reducedMotionRef.current,
        disableFlipByClick: false,
      });
      flipBook.loadFromHTML(root.querySelectorAll<HTMLElement>(".book-sheet"));
      flipBook.on("flip", (event: PageFlipEvent) => {
        const next = Number(event.data);
        currentPageRef.current = next;
        setCurrentPage(next);
        playFlipSound();
        if (!timelineDrivenFlipRef.current) {
          window.setTimeout(() => void playPage(next), reducedMotionRef.current ? 30 : 230);
        }
      });
      pageFlipRef.current = flipBook;
    }
    return () => {
      destroyTimerRef.current = window.setTimeout(() => {
        pageFlipRef.current?.destroy();
        pageFlipRef.current = null;
      }, 0);
    };
  }, [comic.id, manifest.sourceComicVersion, pages.length, playFlipSound, playPage]);

  useEffect(() => () => {
    stopPageAudio();
    if (timelineFlipReleaseRef.current !== null) {
      window.clearTimeout(timelineFlipReleaseRef.current);
    }
    ambientNodesRef.current.splice(0).forEach((node) => {
      try { node.stop(); } catch { /* already stopped during hot reload */ }
    });
    ambientNodesRef.current = [];
    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") void context.close();
  }, [stopPageAudio]);

  const goPrevious = () => {
    const book = pageFlipRef.current;
    if (!book || currentPage <= 0) return;
    if (reducedMotion) book.turnToPrevPage();
    else book.flipPrev("bottom");
  };

  const goNext = () => {
    const book = pageFlipRef.current;
    if (!book || currentPage >= pages.length - 1) return;
    if (reducedMotion) book.turnToNextPage();
    else book.flipNext("bottom");
  };

  const goToPage = (index: number) => {
    const book = pageFlipRef.current;
    if (!book) return;
    if (reducedMotion) book.turnToPage(index);
    else book.flip(index, "bottom");
  };

  return <section className="immersive-book" aria-label="沉浸式家庭电子书">
    <audio
      ref={recordingRef}
      preload="metadata"
      onTimeUpdate={syncExperienceTimeline}
      onEnded={() => {
        setAudioState("已暂停");
        setCurrentLine("故事讲完了，再翻一次也很好。");
      }}
    />
    <div className="book-reader-heading">
      <div><span><BookOpen size={15} />IMMERSIVE FAMILY BOOK</span><strong>一条故事线，带着画面和声音向前走</strong></div>
      <em>{storybook ? `书册 v${storybook.currentVersion} · ${experience ? "连续故事音轨" : "正在编排"}` : "正在建立书册版本"}</em>
    </div>

    <div className="book-room">
      <div className="book-room-light" />
      {!soundStarted && <div className="sound-gate">
        <span><Headphones size={28} /></span>
        <div><strong>开启连续有声故事</strong><small>画面、解说、家人原声和翻页将沿同一时间轴播放</small></div>
        <button onClick={() => void startSound()}><Play size={16} fill="currentColor" />开始阅读</button>
      </div>}

      <div className="book-stage-wrap">
        <div className="book-stage" ref={bookRef}>
          {pages.map((page) => {
            const scene = experience?.scenes.find((item) => item.pageIndex === page.index);
            const pageTitle = scene?.title ?? page.title;
            const pageNarration = scene?.narration ?? page.narration;
            const pageQuote = scene?.quote ?? page.panel?.dialogue;
            if (page.type === "cover") return <article className="book-sheet book-cover" data-density="hard" key="cover">
              <div className="book-cover-art" style={pageBackground(page)} />
              <div className="book-cover-shade" />
              <div className="book-cover-copy"><span>家庭故事豆 · 有声绘本</span><h2>{pageTitle}</h2><p>{pageNarration}</p><small>轻触书角，开始翻阅</small></div>
            </article>;
            if (page.type === "story" && (page.assetUrl || page.panel)) return <article className="book-sheet book-story-page" key={`scene-${page.index}`}>
              <div className="book-page-art" style={pageBackground(page)}>
                <span className="book-page-number">0{page.index}</span>
                {pageQuote && <blockquote>“{pageQuote}”</blockquote>}
                {page.panel && regenerating === page.panel.panel_index && <span className="book-page-regenerating"><RefreshCw className="spin" />正在重画</span>}
              </div>
              <div className="book-page-copy">
                <span className="book-page-kicker">CHAPTER 0{page.index}</span>
                <h2>{pageTitle}</h2>
                <p>{pageNarration}</p>
                <div><span>{scene?.sourceSegmentId || page.panel?.source_segment_id ? <><WavesIcon />{scene?.speakerName ? `${scene.speakerName}原声` : "人物原声"}</> : <><Sparkles size={12} />故事解说</>}</span>{page.panel && <button onClick={(event) => { event.stopPropagation(); void onRegenerate(page.panel!.panel_index); }} disabled={regenerating !== null}><RefreshCw size={12} />重画</button>}</div>
              </div>
            </article>;
            return <article className="book-sheet book-ending" data-density="hard" key="ending">
              <div className="book-ending-art" style={pageBackground(page)} />
              <div className="book-ending-copy"><Sparkles size={28} /><span>THE END, FOR NOW</span><h2>{pageTitle}</h2><p>{pageNarration}</p><small>家庭故事豆 · 记录此刻，留给未来</small></div>
            </article>;
          })}
        </div>
      </div>

      <div className="book-sound-now" aria-live="polite">
        <span className={soundStarted && !muted ? "playing" : ""}><Music2 size={14} /></span>
        <div><small>故事时间线</small><strong>{audioState}</strong></div>
        {currentLine && <p className="book-current-line">{currentLine}</p>}
        {currentPage > 0 && currentPage <= comic.panels.length && <button onClick={() => void playPage(currentPage)}><RotateCcw size={13} />重听这一幕</button>}
      </div>
    </div>

    <div className="book-controls">
      <button className="book-round-button" onClick={goPrevious} disabled={currentPage <= 0} aria-label="上一页"><ChevronLeft /></button>
      <div className="book-progress">
        <span>{currentPage + 1} / {pages.length}</span>
        <div>{pages.map((page) => <button className={page.index === currentPage ? "active" : ""} onClick={() => goToPage(page.index)} key={page.index} aria-label={`第 ${page.index + 1} 页`} />)}</div>
      </div>
      <button className="book-round-button" onClick={goNext} disabled={currentPage >= pages.length - 1} aria-label="下一页"><ChevronRight /></button>
      <span className="book-control-divider" />
      <button className={soundStarted && !muted ? "active" : ""} onClick={() => soundStarted ? toggleMute() : void startSound()}>{muted || !soundStarted ? <VolumeX size={15} /> : <Volume2 size={15} />}{muted || !soundStarted ? "开启声音" : "有声"}</button>
      <button className={musicOn || Boolean(experience) ? "active" : ""} onClick={() => setMusicOn((value) => !value)} disabled={!soundStarted || Boolean(experience)}><Music2 size={15} />故事配乐</button>
      <button className={experience || autoPlay ? "active" : ""} onClick={() => setAutoPlay((value) => !value)} disabled={!soundStarted || Boolean(experience)}>{experience || autoPlay ? <Pause size={15} /> : <FastForward size={15} />}{experience ? "跟随故事" : "自动翻页"}</button>
      <button className={reducedMotion ? "active" : ""} onClick={() => setReducedMotion((value) => !value)}><Sparkles size={15} />柔和动效</button>
    </div>
    <p className="book-prototype-note"><Sparkles size={13} />一条连续故事音轨统一编排 AI 解说、家人原声与背景音乐；图片、文字和翻页由同一时间轴驱动。</p>
  </section>;
}

function WavesIcon() {
  return <span className="book-wave-icon" aria-hidden="true"><i /><i /><i /></span>;
}

import type { Comic } from "../../services/comicApi";

export type StorybookPageType = "cover" | "story" | "ending";

export type StorybookPage = {
  index: number;
  type: StorybookPageType;
  title: string;
  narration: string;
  panelIndex: number | null;
  panelVersion?: number | null;
  clip: {
    sourceSegmentId?: string;
    startMs: number;
    endMs: number;
  } | null;
};

export type StorybookManifest = {
  schemaVersion: "storybook-manifest-v1";
  sourceComicId: string;
  sourceComicVersion: number;
  title: string;
  pageCount: number;
  audio: {
    backgroundMode: string;
    pageTurnMode: string;
    narrationMode: string;
    highlightSource: string;
  };
  pages: StorybookPage[];
};

const storyPageTitles = [
  "一颗会飞的西红柿",
  "番茄拿铁",
  "冠军事故现场",
  "今天最好记的事",
];

const demoClipRanges = [
  { startMs: 33_000, endMs: 37_500 },
  { startMs: 37_500, endMs: 42_500 },
  { startMs: 42_500, endMs: 46_500 },
  null,
];

export function storybookTitle(comic: Comic): string {
  return comic.panels.some((panel) =>
    panel.dialogue?.includes("西红柿") || panel.dialogue?.includes("奶奶家")
  ) ? "会飞的西红柿" : comic.title;
}

export function createPrototypeBookManifest(comic: Comic): StorybookManifest {
  const title = storybookTitle(comic);
  const pages: StorybookPage[] = [
    {
      index: 0,
      type: "cover",
      title,
      narration: `这是一本由家人真实声音做成的故事书。${title}`,
      panelIndex: comic.panels[0]?.panel_index ?? null,
      panelVersion: comic.panels[0]?.version ?? null,
      clip: null,
    },
    ...comic.panels.map((panel, index) => ({
      index: index + 1,
      type: "story" as const,
      title: storyPageTitles[index] ?? `第 ${panel.panel_index} 页`,
      narration: panel.narration,
      panelIndex: panel.panel_index,
      panelVersion: panel.version,
      clip: demoClipRanges[index] ?? null,
    })),
    {
      index: comic.panels.length + 1,
      type: "ending",
      title: "家人的笑声，就是故事的封底",
      narration: "一顿普通的晚餐，因为一颗西红柿，成了一家人会记得很久的快乐时刻。",
      panelIndex: comic.panels.at(-1)?.panel_index ?? null,
      panelVersion: comic.panels.at(-1)?.version ?? null,
      clip: null,
    },
  ];
  return {
    schemaVersion: "storybook-manifest-v1",
    sourceComicId: comic.id,
    sourceComicVersion: comic.version,
    title,
    pageCount: pages.length,
    audio: {
      backgroundMode: "synthesized-prototype",
      pageTurnMode: "synthesized-prototype",
      narrationMode: "browser-speech-prototype",
      highlightSource: "bundled-demo-recording",
    },
    pages,
  };
}

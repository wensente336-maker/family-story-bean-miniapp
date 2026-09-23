import { env } from "../config/env";
import type { StorybookManifest } from "../features/storybook/bookManifest";
import { apiRequest } from "./apiClient";

type StorybookApiPage = {
  index: number;
  type: "cover" | "story" | "ending";
  title: string;
  narration: string;
  panel_index: number | null;
  panel_version: number | null;
  clip: {
    source_segment_id: string;
    start_ms: number;
    end_ms: number;
  } | null;
};

type StorybookApiData = {
  id: string;
  comic_id: string;
  recording_id: string;
  title: string;
  status: string;
  current_version: number;
  schema_version: string;
  source_comic_version: number;
  manifest: {
    schema_version: "storybook-manifest-v1";
    source_comic_id: string;
    source_comic_version: number;
    title: string;
    page_count: number;
    audio: {
      background_mode: string;
      page_turn_mode: string;
      narration_mode: string;
      highlight_source: string;
    };
    pages: StorybookApiPage[];
  };
  created_at: string;
  updated_at: string;
};

export type Storybook = {
  id: string;
  comicId: string;
  recordingId: string;
  title: string;
  status: string;
  currentVersion: number;
  sourceComicVersion: number;
  manifest: StorybookManifest;
  createdAt: string;
  updatedAt: string;
};

export function normalizeStorybook(data: StorybookApiData): Storybook {
  return {
    id: data.id,
    comicId: data.comic_id,
    recordingId: data.recording_id,
    title: data.title,
    status: data.status,
    currentVersion: data.current_version,
    sourceComicVersion: data.source_comic_version,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
    manifest: {
      schemaVersion: data.manifest.schema_version,
      sourceComicId: data.manifest.source_comic_id,
      sourceComicVersion: data.manifest.source_comic_version,
      title: data.manifest.title,
      pageCount: data.manifest.page_count,
      audio: {
        backgroundMode: data.manifest.audio.background_mode,
        pageTurnMode: data.manifest.audio.page_turn_mode,
        narrationMode: data.manifest.audio.narration_mode,
        highlightSource: data.manifest.audio.highlight_source,
      },
      pages: data.manifest.pages.map((page) => ({
        index: page.index,
        type: page.type,
        title: page.title,
        narration: page.narration,
        panelIndex: page.panel_index,
        panelVersion: page.panel_version,
        clip: page.clip ? {
          sourceSegmentId: page.clip.source_segment_id,
          startMs: page.clip.start_ms,
          endMs: page.clip.end_ms,
        } : null,
      })),
    },
  };
}

export async function createOrRefreshStorybook(comicId: string): Promise<Storybook> {
  const data = await apiRequest<StorybookApiData>(
    env.apiBaseUrl,
    `/v1/comics/${comicId}/storybook`,
    { method: "POST" },
  );
  return normalizeStorybook(data);
}

export async function getStorybook(storybookId: string): Promise<Storybook> {
  const data = await apiRequest<StorybookApiData>(
    env.apiBaseUrl,
    `/v1/storybooks/${storybookId}`,
  );
  return normalizeStorybook(data);
}

export type StorybookAudioClip = {
  pageIndex: number;
  sourceSegmentId: string;
  originalStartMs: number;
  originalEndMs: number;
  durationMs: number;
  url: string;
};

export type StorybookAudioSession = {
  storybookId: string;
  version: number;
  sourceRecordingId: string;
  expiresAt: number;
  clips: StorybookAudioClip[];
};

type StorybookAudioSessionApiData = {
  storybook_id: string;
  version: number;
  source_recording_id: string;
  expires_at: number;
  clips: Array<{
    page_index: number;
    source_segment_id: string;
    original_start_ms: number;
    original_end_ms: number;
    duration_ms: number;
    url: string;
  }>;
};

export async function createStorybookAudioSession(
  storybookId: string,
): Promise<StorybookAudioSession> {
  const data = await apiRequest<StorybookAudioSessionApiData>(
    env.apiBaseUrl,
    `/v1/storybooks/${storybookId}/audio-session`,
    { method: "POST" },
  );
  return {
    storybookId: data.storybook_id,
    version: data.version,
    sourceRecordingId: data.source_recording_id,
    expiresAt: data.expires_at,
    clips: data.clips.map((clip) => ({
      pageIndex: clip.page_index,
      sourceSegmentId: clip.source_segment_id,
      originalStartMs: clip.original_start_ms,
      originalEndMs: clip.original_end_ms,
      durationMs: clip.duration_ms,
      url: clip.url,
    })),
  };
}

export type StorybookExperienceScene = {
  pageIndex: number;
  type: "cover" | "story" | "ending";
  title: string;
  narration: string;
  quote: string | null;
  sourceSegmentId: string | null;
  speakerName: string | null;
  sceneKind: string | null;
  storyPurpose: string | null;
  visualDescription: string | null;
  assetUrl: string | null;
  fallbackPanelIndex: number | null;
  imagePrompt: string;
  audioStartMs: number;
  audioEndMs: number;
};

export type StorybookExperienceCue = {
  segmentIndex: number;
  kind: "narration" | "original";
  label: string;
  text: string;
  pageIndex: number;
  startMs: number;
  endMs: number;
  sourceSegmentId: string | null;
};

export type StorybookExperienceSession = {
  storybookId: string;
  version: number;
  sourceRecordingId: string;
  durationMs: number;
  url: string;
  expiresAt: number;
  storylineSchemaVersion: string;
  scenes: StorybookExperienceScene[];
  cues: StorybookExperienceCue[];
  narratorProvider: string | null;
  narratorVoice: string | null;
  musicSource: string | null;
};

type StorybookExperienceSessionApiData = {
  storybook_id: string;
  version: number;
  source_recording_id: string;
  duration_ms: number;
  url: string;
  expires_at: number;
  storyline_schema_version: string;
  scenes: Array<{
    page_index: number;
    type: "cover" | "story" | "ending";
    title: string;
    narration: string;
    quote: string | null;
    source_segment_id: string | null;
    speaker_name: string | null;
    scene_kind: string | null;
    story_purpose: string | null;
    visual_description: string | null;
    asset_url: string | null;
    fallback_panel_index: number | null;
    image_prompt: string;
    audio_start_ms: number;
    audio_end_ms: number;
  }>;
  cues: Array<{
    segment_index: number;
    kind: "narration" | "original";
    label: string;
    text: string;
    page_index: number;
    start_ms: number;
    end_ms: number;
    source_segment_id: string | null;
  }>;
  narrator_provider: string | null;
  narrator_voice: string | null;
  music_source: string | null;
};

export async function createStorybookExperienceSession(
  storybookId: string,
): Promise<StorybookExperienceSession> {
  const data = await apiRequest<StorybookExperienceSessionApiData>(
    env.apiBaseUrl,
    `/v1/storybooks/${storybookId}/experience-session`,
    { method: "POST" },
  );
  return {
    storybookId: data.storybook_id,
    version: data.version,
    sourceRecordingId: data.source_recording_id,
    durationMs: data.duration_ms,
    url: data.url,
    expiresAt: data.expires_at,
    storylineSchemaVersion: data.storyline_schema_version,
    scenes: data.scenes.map((scene) => ({
      pageIndex: scene.page_index,
      type: scene.type,
      title: scene.title,
      narration: scene.narration,
      quote: scene.quote,
      sourceSegmentId: scene.source_segment_id,
      speakerName: scene.speaker_name,
      sceneKind: scene.scene_kind,
      storyPurpose: scene.story_purpose,
      visualDescription: scene.visual_description,
      assetUrl: scene.asset_url,
      fallbackPanelIndex: scene.fallback_panel_index,
      imagePrompt: scene.image_prompt,
      audioStartMs: scene.audio_start_ms,
      audioEndMs: scene.audio_end_ms,
    })),
    cues: data.cues.map((cue) => ({
      segmentIndex: cue.segment_index,
      kind: cue.kind,
      label: cue.label,
      text: cue.text,
      pageIndex: cue.page_index,
      startMs: cue.start_ms,
      endMs: cue.end_ms,
      sourceSegmentId: cue.source_segment_id,
    })),
    narratorProvider: data.narrator_provider,
    narratorVoice: data.narrator_voice,
    musicSource: data.music_source,
  };
}

export type StoryPlanClip = {
  sourceSegmentId: string;
  speakerKey: string;
  speakerName: string;
  startMs: number;
  endMs: number;
  text: string;
  included: boolean;
  locked: boolean;
};

export type StoryPlanScene = {
  sceneIndex: number;
  pageIndex: number;
  type: "cover" | "story" | "ending";
  sceneKind: string;
  storyPurpose: string;
  title: string;
  narration: string;
  quote: string | null;
  sourceSegmentId: string | null;
  speakerName: string | null;
  visualDescription: string;
  imagePrompt: string;
  assetUrl: string | null;
  fallbackPanelIndex: number;
  audioSequence: Array<{ kind: "narration" | "original"; text: string }>;
};

export type StoryPlan = {
  id: string;
  storybookId: string;
  storybookVersionId: string;
  sourceRecordingId: string;
  status: "DRAFT" | "CONFIRMED";
  revision: number;
  narrationStyle: string;
  clips: StoryPlanClip[];
  scenes: StoryPlanScene[];
  createdAt: string;
  updatedAt: string;
};

type StoryPlanApiData = {
  id: string;
  storybook_id: string;
  storybook_version_id: string;
  source_recording_id: string;
  status: "DRAFT" | "CONFIRMED";
  revision: number;
  source_story: {
    narration_style: string;
    clips: Array<{
      source_segment_id: string;
      speaker_key: string;
      speaker_name: string;
      start_ms: number;
      end_ms: number;
      text: string;
      included: boolean;
      locked: boolean;
    }>;
  };
  director_script: {
    scenes: Array<{
      scene_index: number;
      page_index: number;
      type: "cover" | "story" | "ending";
      scene_kind: string;
      story_purpose: string;
      title: string;
      narration: string;
      quote: string | null;
      source_segment_id: string | null;
      speaker_name: string | null;
      visual_description: string;
      image_prompt: string;
      asset_url: string | null;
      fallback_panel_index: number;
      audio_sequence: Array<{ kind: "narration" | "original"; text: string }>;
    }>;
  };
  created_at: string;
  updated_at: string;
};

function normalizeStoryPlan(data: StoryPlanApiData): StoryPlan {
  return {
    id: data.id,
    storybookId: data.storybook_id,
    storybookVersionId: data.storybook_version_id,
    sourceRecordingId: data.source_recording_id,
    status: data.status,
    revision: data.revision,
    narrationStyle: data.source_story.narration_style,
    clips: data.source_story.clips.map((clip) => ({
      sourceSegmentId: clip.source_segment_id,
      speakerKey: clip.speaker_key,
      speakerName: clip.speaker_name,
      startMs: clip.start_ms,
      endMs: clip.end_ms,
      text: clip.text,
      included: clip.included,
      locked: clip.locked,
    })),
    scenes: data.director_script.scenes.map((scene) => ({
      sceneIndex: scene.scene_index,
      pageIndex: scene.page_index,
      type: scene.type,
      sceneKind: scene.scene_kind,
      storyPurpose: scene.story_purpose,
      title: scene.title,
      narration: scene.narration,
      quote: scene.quote,
      sourceSegmentId: scene.source_segment_id,
      speakerName: scene.speaker_name,
      visualDescription: scene.visual_description,
      imagePrompt: scene.image_prompt,
      assetUrl: scene.asset_url,
      fallbackPanelIndex: scene.fallback_panel_index,
      audioSequence: scene.audio_sequence,
    })),
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

export async function createStoryPlanDraft(storybookId: string): Promise<StoryPlan> {
  const data = await apiRequest<StoryPlanApiData>(
    env.apiBaseUrl,
    `/v1/storybooks/${storybookId}/story-plan/draft`,
    { method: "POST" },
  );
  return normalizeStoryPlan(data);
}

export async function updateStoryPlan(
  storybookId: string,
  plan: Pick<StoryPlan, "clips" | "narrationStyle">,
  status: "DRAFT" | "CONFIRMED",
): Promise<StoryPlan> {
  const data = await apiRequest<StoryPlanApiData>(
    env.apiBaseUrl,
    `/v1/storybooks/${storybookId}/story-plan`,
    {
      method: "PATCH",
      body: JSON.stringify({
        clips: plan.clips.map((clip) => ({
          source_segment_id: clip.sourceSegmentId,
          included: clip.included,
        })),
        narration_style: plan.narrationStyle,
        status,
      }),
    },
  );
  return normalizeStoryPlan(data);
}

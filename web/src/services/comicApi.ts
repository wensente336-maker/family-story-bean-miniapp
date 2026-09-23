import { env } from "../config/env";
import { apiRequest } from "./apiClient";

export type ComicPanel = {
  id: string;
  panel_index: number;
  narration: string;
  dialogue: string | null;
  source_segment_id: string | null;
  asset_url: string;
  asset_variant: string;
  crop_x: number;
  crop_y: number;
  prompt: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type Comic = {
  id: string;
  moment_id: string;
  title: string;
  status: string;
  version: number;
  pipeline_version: string;
  metadata: {
    layout?: string;
    visual_bible?: {
      style: string;
      palette: string[];
      characters: Array<{ display_name: string; speaker_key: string }>;
      consistency_rule: string;
    };
  };
  panels: ComicPanel[];
  created_at: string;
  updated_at: string;
};

export function createComic(momentId: string): Promise<Comic> {
  return apiRequest(env.apiBaseUrl, `/v1/moments/${momentId}/comics`, { method: "POST" });
}

export function getComic(comicId: string): Promise<Comic> {
  return apiRequest(env.apiBaseUrl, `/v1/comics/${comicId}`);
}

export function regenerateComicPanel(comicId: string, panelIndex: number): Promise<Comic> {
  return apiRequest(env.apiBaseUrl, `/v1/comics/${comicId}/panels/${panelIndex}/regenerate`, {
    method: "POST"
  });
}

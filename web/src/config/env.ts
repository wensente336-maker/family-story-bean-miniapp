export type DataSource = "mock" | "api";

const configuredSource = import.meta.env.VITE_DATA_SOURCE ?? "api";
const comicCreationEnabled = import.meta.env.VITE_ENABLE_COMIC_CREATION === "true";
const podcastCreationEnabled = import.meta.env.VITE_ENABLE_PODCAST_CREATION !== "false";

export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, ""),
  dataSource: (configuredSource === "api" ? "api" : "mock") as DataSource,
  features: {
    comicCreation: comicCreationEnabled,
    podcastCreation: podcastCreationEnabled,
  },
};

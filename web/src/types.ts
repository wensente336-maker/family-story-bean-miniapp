export type Processing = {
  recordingId?: string;
  jobId?: string;
  title: string;
  detail: string;
  progress: number;
  stage?: string;
};

export type Moment = {
  id: string;
  recordingId: string;
  theme: string;
  duration: string;
  title: string;
  quote: string;
  tone: "honey" | "coral";
  image?: string;
};

export type HomeData = {
  family: { name: string; members: string[] };
  processing: Processing;
  moments: Moment[];
};

import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedApp } from "./auth/ProtectedApp";
import { StatusPanel } from "./components/StatusPanel";
import { FamilyPage } from "./pages/FamilyPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { UploadPage } from "./pages/UploadPage";
import { RecordingProgressPage } from "./pages/RecordingProgressPage";
import { ComicPage } from "./pages/ComicPage";
import { PodcastPage } from "./pages/PodcastPage";
import { TimelinePage } from "./pages/TimelinePageV2";
import { PrivacyPage } from "./pages/PrivacyPage";
import { PublicSharePage } from "./pages/PublicSharePage";
import { PodcastRenderPage } from "./pages/PodcastRenderPage";
import { PodcastProductPage } from "./pages/PodcastProductPage";
import { PodcastLibraryPage } from "./pages/PodcastLibraryPage";
import { PodcastTrashPage } from "./pages/PodcastTrashPage";
import { StoryConfirmationPage } from "./pages/StoryConfirmationPage";
import { HighlightPage } from "./pages/HighlightPage";
import { PublicHighlightSharePage } from "./pages/PublicHighlightSharePage";

const routeCopy = {
  upload: { eyebrow: "声音采集", title: "留下今天的家庭声音", description: "支持音频、视频、手机录音和录音豆导入，内容默认仅家庭空间可见。" },
  recording: { eyebrow: "处理进度", title: "正在识别家人的声音", description: "完成转写后，你可以确认人物、原话和要保留的声音片段。" },
  moment: { eyebrow: "声音素材", title: "确认要留下的家庭原声", description: "确认后的原声会成为 AI 第三人称串讲的唯一事实依据。" },
  comic: { eyebrow: "历史作品", title: "家庭漫画已归档", description: "已有作品继续保留查看和导出；新的家庭故事将以声音播客形式生成。" },
  podcast: { eyebrow: "声音创作", title: "生成家庭播客", description: "用第三人称解说串起家人的真实原声。" }
} as const;

function PlannedPage({ kind }: { kind: keyof typeof routeCopy }) {
  return <StatusPanel {...routeCopy[kind]} />;
}

function LegacyCreationRedirect({ destination }: { destination: "story" | "render" }) {
  const { id = "" } = useParams();
  return <Navigate to={`/recordings/${id}/${destination}`} replace />;
}

function AuthenticatedRoutes() {
  return <ProtectedApp><Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/podcasts" element={<PodcastLibraryPage />} />
    <Route path="/podcasts/trash" element={<PodcastTrashPage />} />
    <Route path="/family" element={<FamilyPage />} />
    <Route path="/upload" element={<UploadPage />} />
    <Route path="/postcards" element={<TimelinePage />} />
    <Route path="/timeline" element={<Navigate to="/postcards" replace />} />
    <Route path="/highlights/:id" element={<HighlightPage />} />
    <Route path="/recordings/:id" element={<RecordingProgressPage />} />
    <Route path="/recordings/:id/story" element={<StoryConfirmationPage />} />
    <Route path="/recordings/:id/transcript" element={<LegacyCreationRedirect destination="story" />} />
    <Route path="/recordings/:id/moments" element={<LegacyCreationRedirect destination="story" />} />
    <Route path="/recordings/:id/materials" element={<LegacyCreationRedirect destination="story" />} />
    <Route path="/recordings/:id/plan" element={<LegacyCreationRedirect destination="story" />} />
    <Route path="/recordings/:id/render" element={<PodcastRenderPage />} />
    <Route path="/recordings/:id/podcast" element={<PodcastProductPage />} />
    <Route path="/moments/:id" element={<PlannedPage kind="moment" />} />
    <Route path="/comics/:id" element={<ComicPage />} />
    <Route path="/podcasts/:id" element={<PodcastPage />} />
    <Route path="/settings/privacy" element={<PrivacyPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></ProtectedApp>;
}

export default function App() {
  return <AuthProvider><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/share/:token" element={<PublicSharePage />} />
    <Route path="/highlight-share/:token" element={<PublicHighlightSharePage />} />
    <Route path="*" element={<AuthenticatedRoutes />} />
  </Routes></AuthProvider>;
}

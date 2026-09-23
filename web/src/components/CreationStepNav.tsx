import { Check } from "lucide-react";
import { useNavigate } from "react-router-dom";

type CreationStepNavProps = {
  current: 1 | 2 | 3;
  recordingId?: string;
  processing?: boolean;
};

const steps = [
  { number: 1, label: "添加素材" },
  { number: 2, label: "确认故事" },
  { number: 3, label: "试听发布" },
] as const;

export function CreationStepNav({ current, recordingId, processing = false }: CreationStepNavProps) {
  const navigate = useNavigate();
  const routeFor = (step: number) => {
    if (step === 1) return recordingId ? `/recordings/${recordingId}` : "/upload";
    if (step === 2 && recordingId) return `/recordings/${recordingId}/story`;
    if (step === 3 && recordingId) return `/recordings/${recordingId}/render`;
    return "";
  };

  return <nav className="creation-step-nav" aria-label="家庭播客创作进度">
    <div className="creation-step-mobile" aria-label={`第 ${current} 步，${steps[current - 1].label}`}>
      <span>第 {current}/3 步</span>
      <strong>{steps[current - 1].label}{processing ? " · 处理中" : ""}</strong>
    </div>
    <ol>{steps.map((step) => {
      const completed = step.number < current;
      const active = step.number === current;
      const route = routeFor(step.number);
      const canVisit = completed && Boolean(route);
      return <li key={step.number} className={`${completed ? "completed" : ""} ${active ? "active" : ""}`}>
        <button type="button" disabled={!canVisit} onClick={() => canVisit && navigate(route)} aria-current={active ? "step" : undefined}>
          <span>{completed ? <Check size={14} /> : step.number}</span>
          <strong>{step.label}</strong>
          {active && <small>{processing ? "正在处理" : "正在进行"}</small>}
        </button>
      </li>;
    })}</ol>
  </nav>;
}

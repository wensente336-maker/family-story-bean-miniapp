import { ArrowLeft, Construction } from "lucide-react";
import { Link } from "react-router-dom";

export function StatusPanel({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <section className="status-panel">
      <div className="status-mark"><Construction size={30} /></div>
      <span className="section-kicker">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
      <Link className="secondary-button" to="/"><ArrowLeft size={18} />返回故事首页</Link>
    </section>
  );
}

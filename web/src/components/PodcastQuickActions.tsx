import { useEffect, useId, useRef, useState } from "react";
import { MoreHorizontal, Pencil, Share2, Trash2 } from "lucide-react";

export function PodcastQuickActions({ title, onEdit, onShare, onDelete }: {
  title: string; onEdit: () => void; onShare: () => void; onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const choose = (action: () => void) => { setOpen(false); trigger.current?.focus(); action(); };
  return <div ref={root} className={`podcast-quick-actions ${open ? "is-open" : ""}`}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false); }}
    onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
      if (open && ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const items = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items[next]?.focus();
      }
    }}>
    <button ref={trigger} className="podcast-menu-trigger" aria-label={`管理作品：${title}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen((value) => !value)} onKeyDown={(event) => { if (event.key === "ArrowDown" && !open) { event.preventDefault(); setOpen(true); } }}><MoreHorizontal size={22} /></button>
    {open && <div id={id} role="menu" aria-label="作品操作" className="podcast-action-menu">
      <button role="menuitem" onClick={() => choose(onEdit)}><Pencil size={16} />编辑</button>
      <button role="menuitem" onClick={() => choose(onShare)}><Share2 size={16} />分享</button>
      <button role="menuitem" className="danger-quiet" onClick={() => choose(onDelete)}><Trash2 size={16} />删除</button>
    </div>}
  </div>;
}

import { ReactNode, useEffect } from "react";

export function Modal({
  title, onClose, children, wide,
}: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={"modal" + (wide ? " modal-wide" : "")}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть">✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

const STATUS_CLASS: Record<string, string> = {
  new: "gray", reminded_24h: "yellow", reminded_sms: "yellow",
  confirmed: "green", done: "blue", rescheduled: "purple",
  cancelled: "gray", no_show: "red",
  active: "green", onboarding: "yellow", grace: "yellow", paused: "red", archived: "gray",
  sleeping: "yellow", lost: "red", excluded: "gray",
  sent: "green", stub: "purple", failed: "red",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  return <span className={`badge badge-${STATUS_CLASS[value] ?? "gray"}`}>{label ?? value}</span>;
}

export function Tabs({
  tabs, active, onChange,
}: { tabs: [string, string][]; active: string; onChange: (key: string) => void }) {
  return (
    <div className="tabs">
      {tabs.map(([key, label]) => (
        <button key={key} className={"tab" + (key === active ? " tab-active" : "")}
                onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner">Загрузка…</div>;
}

export function Empty({ text = "Пока пусто" }: { text?: string }) {
  return <div className="empty">{text}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function Pager({
  page, total, pageSize, onPage,
}: { page: number; total: number; pageSize: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => onPage(page - 1)}>←</button>
      <span>{page} / {pages}</span>
      <button disabled={page >= pages} onClick={() => onPage(page + 1)}>→</button>
    </div>
  );
}

export const money = (n: number) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " ₽";

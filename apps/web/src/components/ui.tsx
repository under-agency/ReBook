import {
  ButtonHTMLAttributes, ReactNode, useEffect, useId, useRef,
} from "react";
import { Inbox, X } from "lucide-react";
import {
  GlyphArrow, GlyphCheck, GlyphCross, GlyphHalf, GlyphRing, GlyphSlash, GlyphSolid,
} from "./icons";

/* ═══ Кнопка ═════════════════════════════════════════════════════════════ */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "sm" | "md";
  icon?: boolean;
};

export function Button({
  variant = "default", size = "md", icon, className = "", type = "button", ...rest
}: ButtonProps) {
  const cls = [
    "btn",
    variant !== "default" ? `btn-${variant}` : "",
    size === "sm" ? "btn-sm" : "",
    icon ? "btn-icon" : "",
    className,
  ].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...rest} />;
}

/* ═══ Диалог ═════════════════════════════════════════════════════════════ */

export function Modal({
  title, onClose, children, wide,
}: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    restoreTo.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusables = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => el.offsetParent !== null);

    focusables()[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      // Ловушка фокуса: Tab не должен уводить за пределы диалога
      const list = focusables();
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !ref.current?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      restoreTo.current?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop"
         onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className={"modal" + (wide ? " modal-wide" : "")}
           role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h3 id={titleId}>{title}</h3>
          <Button variant="ghost" size="sm" icon onClick={onClose} aria-label="Закрыть">
            <X size={15} />
          </Button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

/* ═══ Статусы ════════════════════════════════════════════════════════════
   Форма несёт смысл наравне с цветом: статус читается и в ч/б, и дальтоником.
   Насыщенный цвет — только у состояний, по которым нужно действовать. */

type Tone = "ok" | "warn" | "danger" | "mute";
type Shape = "ring" | "half" | "check" | "solid" | "cross" | "slash" | "arrow";

const STATUS_LOOK: Record<string, [Shape, Tone]> = {
  // записи
  new: ["ring", "mute"],
  reminded_24h: ["half", "warn"],
  reminded_sms: ["half", "warn"],
  confirmed: ["check", "ok"],
  done: ["solid", "mute"],
  rescheduled: ["arrow", "mute"],
  cancelled: ["slash", "mute"],
  no_show: ["cross", "danger"],
  // салоны
  onboarding: ["half", "warn"],
  active: ["check", "ok"],
  grace: ["half", "warn"],
  paused: ["slash", "danger"],
  archived: ["solid", "mute"],
  // клиенты
  sleeping: ["half", "warn"],
  lost: ["cross", "danger"],
  excluded: ["slash", "mute"],
  // доставка
  sent: ["check", "ok"],
  stub: ["ring", "mute"],
  failed: ["cross", "danger"],
};

const SHAPES: Record<Shape, (p: { size?: number }) => JSX.Element> = {
  ring: GlyphRing, half: GlyphHalf, check: GlyphCheck, solid: GlyphSolid,
  cross: GlyphCross, slash: GlyphSlash, arrow: GlyphArrow,
};

export function Status({ value, label }: { value: string; label?: string }) {
  const [shape, tone] = STATUS_LOOK[value] ?? ["ring", "mute"];
  const Glyph = SHAPES[shape];
  return (
    <span className={`status status-${tone}`}>
      <Glyph />
      <span className="status-label">{label ?? value}</span>
    </span>
  );
}

/** Мелкая нейтральная метка: канал, тип сообщения, «поддержка». */
export function Tag({ children, tone }: { children: ReactNode; tone?: Tone }) {
  return <span className={"chip" + (tone === "danger" ? " chip-active" : "")}>{children}</span>;
}

/* ═══ Табы ═══════════════════════════════════════════════════════════════ */

export function Tabs({
  tabs, active, onChange,
}: { tabs: [string, string][]; active: string; onChange: (key: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" aria-selected={key === active}
                className={"tab" + (key === active ? " tab-active" : "")}
                onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

/* ═══ Загрузка ═══════════════════════════════════════════════════════════ */

export function Skeleton({ w, h = 12 }: { w: number | string; h?: number }) {
  return <span className="skeleton" style={{ display: "block", width: w, height: h }} />;
}

/** Каркас таблицы вместо подмены всего экрана словом «Загрузка…» */
export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  const widths = ["22%", "34%", "18%", "26%", "20%", "30%", "16%"];
  return (
    <div className="skel-rows" aria-hidden>
      {Array.from({ length: rows }, (_, r) => (
        <div className="skel-row" key={r}>
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} w={widths[(r + c) % widths.length]} h={10} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner">Загрузка…</div>;
}

/* ═══ Пустое состояние ═══════════════════════════════════════════════════ */

export function Empty({
  text = "Пока пусто", hint, action,
}: { text?: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <Inbox size={22} strokeWidth={1.5} />
      <span className="empty-title">{text}</span>
      {hint && <span>{hint}</span>}
      {action}
    </div>
  );
}

/* ═══ Ошибка загрузки ════════════════════════════════════════════════════ */

export function LoadError({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="empty">
      <span className="empty-title">Не удалось загрузить данные</span>
      <span>Проверьте соединение и попробуйте ещё раз.</span>
      {onRetry && <Button className="mt-2" onClick={onRetry}>Повторить</Button>}
    </div>
  );
}

/* ═══ Форма и пагинация ══════════════════════════════════════════════════ */

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
      <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Назад</Button>
      <span className="mono">{page} / {pages}</span>
      <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Вперёд</Button>
    </div>
  );
}

/* ═══ Форматирование ═════════════════════════════════════════════════════ */

export const money = (n: number) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " ₽";

/** Строка таблицы, открываемая мышью и с клавиатуры. */
export function rowProps(onOpen: () => void) {
  return {
    className: "clickable",
    tabIndex: 0,
    onClick: onOpen,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onOpen();
      }
    },
  };
}

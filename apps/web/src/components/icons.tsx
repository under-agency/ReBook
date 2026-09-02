/* Собственные глифы: в библиотеках их нет, и именно они несут характер.
   Форма несёт смысл наравне с цветом — статус читается и без цвета. */

type G = { size?: number };

const box = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 16 16",
  fill: "none",
  xmlns: "http://www.w3.org/2000/svg",
  "aria-hidden": true as const,
});

/* ── Статусные глифы ──────────────────────────────────────────────────── */

/** Пустое кольцо — ничего не происходило (new) */
export function GlyphRing({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/** Кольцо, залитое наполовину — ждём ответ (reminded_*) */
export function GlyphHalf({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 3.5A4.5 4.5 0 0 1 8 12.5Z" fill="currentColor" />
    </svg>
  );
}

/** Кольцо с галочкой — клиент подтвердил (confirmed) */
export function GlyphCheck({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5.8 8.1 7.3 9.6 10.2 6.6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Залитый круг — визит состоялся (done) */
export function GlyphSolid({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" fill="currentColor" />
    </svg>
  );
}

/** Кольцо с крестом — неявка (no_show) */
export function GlyphCross({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="m6.2 6.2 3.6 3.6M9.8 6.2 6.2 9.8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Кольцо с диагональю — отменена (cancelled) */
export function GlyphSlash({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4.9 11.1 11.1 4.9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/** Кольцо со стрелкой — перенесена (rescheduled) */
export function GlyphArrow({ size = 13 }: G) {
  return (
    <svg {...box(size)}>
      <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5.9 8h4.2M8.6 6.5 10.1 8l-1.5 1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ── Цепочка каскада ──────────────────────────────────────────────────────
   Три узла: напоминание за 24 ч → второе касание (SMS) → ответ клиента.
   Состояние выводится из booking.status, дополнительных запросов не нужно. */

export type CascadeState = "none" | "first" | "second" | "answered" | "closed";

export function cascadeFromStatus(status: string): CascadeState | null {
  switch (status) {
    case "new":
      return "none";
    case "reminded_24h":
      return "first";
    case "reminded_sms":
      return "second";
    case "confirmed":
    case "done":
      return "answered";
    case "cancelled":
    case "no_show":
    case "rescheduled":
      return "closed";
    default:
      return null;
  }
}

const CASCADE_TITLE: Record<CascadeState, string> = {
  none: "Напоминаний ещё не было",
  first: "Ушло напоминание за 24 ч, ответа нет",
  second: "Ушло второе касание, ответа нет",
  answered: "Клиент ответил на напоминание",
  closed: "Каскад закрыт",
};

export function CascadeChain({ state }: { state: CascadeState }) {
  // Сколько узлов «горит» и каким цветом
  const filled = { none: 0, first: 1, second: 2, answered: 2, closed: 0 }[state];
  const answered = state === "answered";
  const nodeCls = (i: number) =>
    answered && i < 2 ? "cascade-done" : i < filled ? "cascade-on" : "cascade-off";

  return (
    <span className="cascade" title={CASCADE_TITLE[state]}>
      <svg width="42" height="12" viewBox="0 0 42 12" fill="none" role="img"
           aria-label={CASCADE_TITLE[state]}>
        <line x1="8" y1="6" x2="13" y2="6"
              className={filled > 1 || answered ? "cascade-link-on" : "cascade-link"} />
        <line x1="24" y1="6" x2="29" y2="6"
              className={answered ? "cascade-link-on" : "cascade-link"} />
        <circle cx="5" cy="6" r="3" className={nodeCls(0)} />
        <circle cx="18.5" cy="6" r="3" className={nodeCls(1)} />
        {answered ? (
          <>
            <circle cx="34" cy="6" r="3.5" className="cascade-done" />
            <path d="m32.4 6 1.2 1.2 2.2-2.4" stroke="var(--surface)" strokeWidth="1.3"
                  strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </>
        ) : (
          <circle cx="34" cy="6" r="3" className="cascade-off" />
        )}
      </svg>
    </span>
  );
}

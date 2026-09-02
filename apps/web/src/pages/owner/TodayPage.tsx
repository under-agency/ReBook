import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronRight, Plus } from "lucide-react";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { PageActions } from "../../components/Layout";
import { CascadeChain, cascadeFromStatus } from "../../components/icons";
import {
  Button, Empty, LoadError, Status, TableSkeleton, money,
} from "../../components/ui";
import BookingModal from "./BookingModal";
import NewBookingModal from "./NewBookingModal";

type Booking = {
  id: number;
  starts_at: string;
  duration_min: number;
  status: string;
  status_display: string;
  customer: { id: number; name: string | null; phone: string | null; has_tg: boolean } | null;
  service: { id: number; name: string; price: number } | null;
  staff: { id: number; name: string } | null;
};

const WAITING = ["new", "reminded_24h", "reminded_sms"];
const OPEN = [...WAITING, "confirmed"];

/* ── Лента дня: время как хребет экрана, разрывы видны ─────────────────── */

function DayFeed({
  items, onOpen, now,
}: { items: Booking[]; onOpen: (id: number) => void; now: dayjs.Dayjs }) {
  if (!items.length) {
    return <Empty text="Записей нет" hint="Свободный день — хороший повод разбудить спящую базу." />;
  }
  return (
    <div className="day">
      {items.map((b, i) => {
        const start = dayjs(b.starts_at);
        const end = start.add(b.duration_min, "minute");
        const prev = i > 0 ? dayjs(items[i - 1].starts_at).add(items[i - 1].duration_min, "minute") : null;
        const gap = prev ? start.diff(prev, "minute") : 0;
        const past = end.isBefore(now);
        const cascade = cascadeFromStatus(b.status);

        return (
          <div key={b.id}>
            {gap >= 20 && (
              <div className="day-gap">
                <span>{prev!.format("HH:mm")}</span>
                <span>окно {gap} мин — можно предложить из листа ожидания</span>
              </div>
            )}
            <button className={"day-row" + (past ? " day-row-past" : "")}
                    onClick={() => onOpen(b.id)}>
              <span className="day-time">
                {start.format("HH:mm")}
                <small>{b.duration_min} мин</small>
              </span>
              <span className="day-main">
                <span className="day-who">{b.customer?.name ?? "Без имени"}</span>
                <span className="day-what">
                  {b.service?.name}
                  {b.staff?.name ? ` · ${b.staff.name}` : ""}
                  {b.customer?.phone ? ` · ${b.customer.phone}` : " · без телефона"}
                </span>
              </span>
              <span className="day-side">
                {cascade && <CascadeChain state={cascade} />}
                <Status value={b.status} label={b.status_display} />
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

/* ── Строка внимания: только то, по чему надо действовать ──────────────── */

function Attention({
  today, tomorrow, now,
}: { today: Booking[]; tomorrow: Booking[]; now: dayjs.Dayjs }) {
  const navigate = useNavigate();
  const day = (d: dayjs.Dayjs) => d.format("YYYY-MM-DD");

  const waitingTomorrow = tomorrow.filter((b) => WAITING.includes(b.status));
  const unclosed = today.filter(
    (b) => OPEN.includes(b.status) && dayjs(b.starts_at).add(b.duration_min, "minute").isBefore(now),
  );
  const unreachable = [...today, ...tomorrow].filter(
    (b) => OPEN.includes(b.status) && !b.customer?.phone && !b.customer?.has_tg,
  );

  const items: { key: string; n: number; text: string; tone: string; go: () => void }[] = [];
  if (waitingTomorrow.length) {
    items.push({
      key: "wait", n: waitingTomorrow.length, tone: "attn-warn",
      text: "не подтвердили визит на завтра — стоит позвонить",
      go: () => navigate(
        `/bookings?date_from=${day(now.add(1, "day"))}&date_to=${day(now.add(1, "day"))}` +
        `&status=${WAITING.join(",")}`,
      ),
    });
  }
  if (unclosed.length) {
    items.push({
      key: "close", n: unclosed.length, tone: "attn-danger",
      text: "визитов прошло без итога — отметьте «состоялась» или «неявка»",
      go: () => navigate(`/bookings?date_from=${day(now)}&date_to=${day(now)}&status=${OPEN.join(",")}`),
    });
  }
  if (unreachable.length) {
    items.push({
      key: "unreach", n: unreachable.length, tone: "attn-warn",
      text: "клиентов без телефона и без мессенджера — напоминание не дойдёт",
      go: () => navigate("/customers"),
    });
  }

  if (!items.length) {
    return (
      <div className="attention">
        <span className="attn attn-calm" style={{ cursor: "default" }}>
          <Check size={16} strokeWidth={2.5} style={{ color: "var(--ok)" }} />
          Всё под контролем: подтверждения собраны, итоги проставлены
        </span>
      </div>
    );
  }

  return (
    <div className="attention">
      {items.map((it) => (
        <button key={it.key} className={`attn ${it.tone}`} onClick={it.go}>
          <span className="attn-count">{it.n}</span>
          {it.text}
          <ChevronRight size={14} className="dim" />
        </button>
      ))}
    </div>
  );
}

/* ── Экран ────────────────────────────────────────────────────────────── */

export default function TodayPage() {
  const navigate = useNavigate();
  const { me } = useAuth();
  // Администратор на ресепшене не видит выручку и отчёты (docs/10-crm-logic.md)
  const seesMoney = me?.user.role !== "staff";
  const [showNew, setShowNew] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [showTomorrow, setShowTomorrow] = useState(true);
  const [now, setNow] = useState(() => dayjs());

  // Экран стоит на ресепшене весь день — держим его живым
  useEffect(() => {
    const t = window.setInterval(() => setNow(dayjs()), 60_000);
    return () => window.clearInterval(t);
  }, []);

  const month = dayjs().format("YYYY-MM");
  const summary = useQuery({
    queryKey: ["summary", month],
    enabled: seesMoney,
    queryFn: () => api<any>(`/api/dashboard/summary?month=${month}`),
  });
  const upcoming = useQuery({
    queryKey: ["upcoming"],
    queryFn: () => api<{ today: Booking[]; tomorrow: Booking[] }>("/api/dashboard/upcoming"),
    refetchInterval: 60_000,
  });

  const s = summary.data ?? {};
  const monthStart = dayjs().startOf("month").format("YYYY-MM-DD");
  const monthEnd = dayjs().endOf("month").format("YYYY-MM-DD");
  const go = (status?: string) =>
    navigate(`/bookings?date_from=${monthStart}&date_to=${monthEnd}` + (status ? `&status=${status}` : ""));

  const today = upcoming.data?.today ?? [];
  const tomorrow = upcoming.data?.tomorrow ?? [];

  return (
    <>
      <PageActions>
        <Button variant="primary" size="sm" onClick={() => setShowNew(true)}>
          <Plus size={14} /> Новая запись
        </Button>
      </PageActions>

      {upcoming.isError ? (
        <LoadError onRetry={() => upcoming.refetch()} />
      ) : upcoming.isLoading ? (
        <TableSkeleton rows={7} cols={3} />
      ) : (
        <>
          <Attention today={today} tomorrow={tomorrow} now={now} />

          <div className="section-head">
            <h2>Сегодня, {now.format("D MMMM")}</h2>
            <span className="push">{today.length} записей</span>
          </div>
          <DayFeed items={today} onOpen={setOpenId} now={now} />

          <div className="section-head">
            <button className="collapse-head" aria-expanded={showTomorrow}
                    onClick={() => setShowTomorrow(!showTomorrow)}>
              <ChevronRight size={16} />
              Завтра, {now.add(1, "day").format("D MMMM")}
            </button>
            <span className="push">{tomorrow.length} записей</span>
          </div>
          {showTomorrow && <DayFeed items={tomorrow} onOpen={setOpenId} now={now} />}

          {/* Витрина для владельца — ниже рабочей части, а не вместо неё */}
          {seesMoney && (
            <>
          <div className="section-head">
            <h2>Месяц · {now.format("MMMM")}</h2>
            <span className="push">каждая цифра кликается до списка записей</span>
          </div>
          <div className="metrics">
            <button className="metric" onClick={() => go()}>
              <span className="m-label">Записей</span>
              <span className="m-value">{s.bookings_total ?? "—"}</span>
            </button>
            <button className="metric" onClick={() => go("confirmed,done")}>
              <span className="m-label">Подтверждено</span>
              <span className="m-value">{s.confirmed ?? "—"}</span>
            </button>
            <button className="metric" onClick={() => go("no_show")}>
              <span className="m-label">Неявки</span>
              <span className="m-value">{s.no_show ?? "—"}</span>
            </button>
            <button className="metric metric-accent" onClick={() => navigate(`/reports/${month}`)}>
              <span className="m-label">Возвращено ≈</span>
              <span className="m-value">{money(s.returned_total ?? 0)}</span>
            </button>
          </div>
            </>
          )}
        </>
      )}

      {showNew && <NewBookingModal onClose={() => setShowNew(false)} />}
      {openId !== null && <BookingModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

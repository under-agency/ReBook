import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs, { Dayjs } from "dayjs";
import { useMemo, useState } from "react";
import { api, errorText } from "../../api/client";
import { useToast } from "../../components/toast";
import { LoadError, TableSkeleton } from "../../components/ui";
import type { NewBookingPreset } from "./NewBookingModal";

const HOUR_PX = 52;
const SNAP_MIN = 15;
const DEFAULT_FROM = 9;
const DEFAULT_TO = 20;

/** Отменённые и перенесённые больше не занимают слот — в сетке им не место. */
const OCCUPIES = ["new", "reminded_24h", "reminded_sms", "confirmed", "done", "no_show"];

type Booking = {
  id: number;
  starts_at: string;
  duration_min: number;
  status: string;
  status_display: string;
  customer: { name: string | null } | null;
  service: { name: string } | null;
  staff: { id: number; name: string } | null;
};

type Span = { b: Booking; start: number; end: number };
type Placed = { b: Booking; lane: number; span: number; lanes: number };

/**
 * Раскладка пересекающихся записей: сначала жадно раздаём дорожки, затем
 * растягиваем каждую запись вправо, пока не упрёмся в соседа. Без второго шага
 * плотный день превращается в частокол из нечитаемых полосок.
 */
function packLanes(items: Booking[]): Placed[] {
  const spans: Span[] = items
    .map((b) => {
      const start = dayjs(b.starts_at).valueOf();
      return { b, start, end: start + b.duration_min * 60_000 };
    })
    .sort((x, y) => x.start - y.start || y.end - x.end);

  const out: Placed[] = [];
  let cluster: Span[] = [];
  let clusterEnd = -Infinity;

  const flush = () => {
    if (!cluster.length) return;
    const laneEnds: number[] = [];
    const lanes: { span: Span; lane: number }[] = [];

    for (const s of cluster) {
      let lane = laneEnds.findIndex((e) => e <= s.start);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(s.end);
      } else {
        laneEnds[lane] = s.end;
      }
      lanes.push({ span: s, lane });
    }

    const total = laneEnds.length;
    for (const { span: s, lane } of lanes) {
      let width = 1;
      while (lane + width < total) {
        const blocked = lanes.some(
          (o) => o.lane === lane + width && o.span.start < s.end && o.span.end > s.start,
        );
        if (blocked) break;
        width += 1;
      }
      out.push({ b: s.b, lane, span: width, lanes: total });
    }

    cluster = [];
    clusterEnd = -Infinity;
  };

  for (const s of spans) {
    if (cluster.length && s.start >= clusterEnd) flush();
    cluster.push(s);
    clusterEnd = Math.max(clusterEnd, s.end);
  }
  flush();
  return out;
}

/** Полоса слева от события: цвет только там, где нужно действие. */
function tone(status: string) {
  if (status === "no_show") return " cal-ev-danger";
  if (status === "confirmed" || status === "done") return " cal-ev-ok";
  if (status === "reminded_24h" || status === "reminded_sms") return " cal-ev-warn";
  return "";
}

export default function BookingsCalendar({
  weekStart, staffId, onOpen, onCreate,
}: {
  weekStart: Dayjs;
  staffId: string;
  onOpen: (id: number) => void;
  onCreate: (preset: NewBookingPreset) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropCol, setDropCol] = useState<number | null>(null);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => weekStart.add(i, "day")),
    [weekStart],
  );
  const from = weekStart.format("YYYY-MM-DD");
  const to = weekStart.add(6, "day").format("YYYY-MM-DD");

  const q = useQuery({
    queryKey: ["calendar", from, to, staffId],
    queryFn: () => api<{ items: Booking[] }>(
      `/api/bookings?date_from=${from}&date_to=${to}&page_size=200` +
      (staffId ? `&staff_id=${staffId}` : ""),
    ),
  });

  const items = useMemo(
    () => (q.data?.items ?? []).filter((b) => OCCUPIES.includes(b.status)),
    [q.data],
  );
  const hidden = (q.data?.items?.length ?? 0) - items.length;

  // Границы сетки берём из самих записей — настройки салона недоступны роли staff
  const [hourFrom, hourTo] = useMemo(() => {
    if (!items.length) return [DEFAULT_FROM, DEFAULT_TO];
    let lo = DEFAULT_FROM;
    let hi = DEFAULT_TO;
    for (const b of items) {
      const s = dayjs(b.starts_at);
      const e = s.add(b.duration_min, "minute");
      lo = Math.min(lo, s.hour());
      hi = Math.max(hi, e.minute() ? e.hour() + 1 : e.hour());
    }
    return [Math.max(0, lo), Math.min(24, Math.max(hi, lo + 1))];
  }, [items]);

  const hours = Array.from({ length: hourTo - hourFrom }, (_, i) => hourFrom + i);
  const gridHeight = hours.length * HOUR_PX;
  const topOf = (d: Dayjs) => ((d.hour() - hourFrom) * 60 + d.minute()) / 60 * HOUR_PX;

  const move = async (id: number, startsAt: string, force = false) => {
    const b = items.find((x) => x.id === id);
    try {
      await api(`/api/bookings/${id}/reschedule`, {
        method: "POST",
        body: { starts_at: startsAt, staff_id: b?.staff?.id ?? null, force },
      });
      qc.invalidateQueries({ queryKey: ["calendar"] });
      qc.invalidateQueries({ queryKey: ["bookings"] });
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      toast.ok(`Перенесли на ${dayjs(startsAt).format("D MMMM, HH:mm")}`);
    } catch (e: any) {
      if (e.status === 409 && e.detail?.warnings) {
        // Конфликт не блокируем жёстко — решает администратор (docs/10-crm-logic.md)
        if (window.confirm(`${e.detail.warnings.join("; ")}\n\nВсё равно перенести?`)) {
          await move(id, startsAt, true);
        }
      } else {
        toast.error(errorText(e));
      }
    }
  };

  const onDrop = (e: React.DragEvent, day: Dayjs) => {
    e.preventDefault();
    setDropCol(null);
    if (dragId === null) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const minutes = ((e.clientY - rect.top) / HOUR_PX) * 60 + hourFrom * 60;
    const snapped = Math.round(minutes / SNAP_MIN) * SNAP_MIN;
    const target = day.startOf("day").add(snapped, "minute");
    setDragId(null);
    move(dragId, target.toISOString());
  };

  if (q.isError) return <LoadError onRetry={() => q.refetch()} />;
  if (q.isLoading) return <TableSkeleton rows={8} cols={7} />;

  return (
    <>
      <div className="cal-wrap">
        <div className="cal-scroll">
          <div className="cal" style={{ gridTemplateColumns: "56px repeat(7, minmax(94px, 1fr))" }}>
            <div className="cal-th" />
            {days.map((d) => (
              <div key={d.toString()}
                   className={"cal-th" + (d.isSame(dayjs(), "day") ? " cal-th-today" : "")}>
                {d.format("dd")}
                <small>{d.format("D MMM")}</small>
              </div>
            ))}

            <div className="cal-gutter">
              {hours.map((h) => (
                <div className="cal-hour" key={h} style={{ height: HOUR_PX }}>
                  {String(h).padStart(2, "0")}:00
                </div>
              ))}
            </div>

            {days.map((day, ci) => {
              const dayItems = items.filter((b) => dayjs(b.starts_at).isSame(day, "day"));
              const isToday = day.isSame(dayjs(), "day");
              return (
                <div key={day.toString()}
                     className={"cal-col" + (dropCol === ci ? " cal-col-drop" : "")}
                     style={{ height: gridHeight }}
                     onDragOver={(e) => { e.preventDefault(); setDropCol(ci); }}
                     onDragLeave={() => setDropCol((c) => (c === ci ? null : c))}
                     onDrop={(e) => onDrop(e, day)}>
                  {hours.map((h) => (
                    <div className="cal-slot" key={h} style={{ height: HOUR_PX }}
                         onClick={() => onCreate({
                           date: day.format("YYYY-MM-DD"),
                           staffId: staffId ? Number(staffId) : undefined,
                         })} />
                  ))}

                  {isToday && dayjs().hour() >= hourFrom && dayjs().hour() < hourTo && (
                    <div className="cal-now" style={{ top: topOf(dayjs()) }} />
                  )}

                  {packLanes(dayItems).map(({ b, lane, span, lanes }) => {
                    const s = dayjs(b.starts_at);
                    const w = 100 / lanes;
                    const narrow = span * w < 45;
                    return (
                      <button key={b.id}
                              className={"cal-ev" + tone(b.status) +
                                         (dragId === b.id ? " cal-ev-dragging" : "")}
                              style={{
                                top: topOf(s),
                                height: Math.max(24, (b.duration_min / 60) * HOUR_PX - 2),
                                left: `calc(${lane * w}% + 2px)`,
                                width: `calc(${span * w}% - 4px)`,
                              }}
                              draggable
                              onDragStart={() => setDragId(b.id)}
                              onDragEnd={() => { setDragId(null); setDropCol(null); }}
                              onClick={() => onOpen(b.id)}
                              title={`${s.format("HH:mm")} · ${b.customer?.name ?? ""} · ` +
                                     `${b.service?.name ?? ""}${b.staff?.name ? ` · ${b.staff.name}` : ""}` +
                                     ` · ${b.status_display}`}>
                        <span className="cal-ev-who">{b.customer?.name ?? "Без имени"}</span>
                        {!narrow && (
                          <>
                            <span className="cal-ev-time">{s.format("HH:mm")}</span>
                            <span className="cal-ev-what">
                              {b.service?.name}{b.staff?.name ? ` · ${b.staff.name}` : ""}
                            </span>
                          </>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <p className="hint mt-2">
        Клик по пустой ячейке — новая запись, перетаскивание — перенос.
        {hidden > 0 && ` Отменённых и перенесённых скрыто: ${hidden} — они в списке.`}
      </p>
    </>
  );
}

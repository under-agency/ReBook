import { keepPreviousData, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CalendarDays, ChevronLeft, ChevronRight, LayoutList, Plus } from "lucide-react";
import { api } from "../../api/client";
import { PageActions } from "../../components/Layout";
import { CascadeChain, cascadeFromStatus } from "../../components/icons";
import {
  Button, Empty, LoadError, Pager, Status, TableSkeleton, rowProps,
} from "../../components/ui";
import BookingModal from "./BookingModal";
import BookingsCalendar from "./BookingsCalendar";
import NewBookingModal, { type NewBookingPreset } from "./NewBookingModal";

const STATUS_OPTIONS: [string, string][] = [
  ["new", "Новая"], ["reminded_24h", "Ждём ответ"], ["reminded_sms", "Ждём ответ (SMS)"],
  ["confirmed", "Придёт"], ["done", "Состоялась"], ["rescheduled", "Перенесена"],
  ["cancelled", "Отменена"], ["no_show", "Неявка"],
];

const SOURCE_LABELS: Record<string, string> = {
  bot: "бот", manual: "вручную", yclients: "YCLIENTS",
};

export default function BookingsPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [newPreset, setNewPreset] = useState<NewBookingPreset | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any>("/api/settings/staff") });

  const view = params.get("view") === "week" ? "week" : "list";
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";
  const status = params.get("status") ?? "";
  const staffId = params.get("staff_id") ?? "";
  const weekStart = dayjs(params.get("week") || undefined).startOf("week");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  const shiftWeek = (n: number) =>
    setParam("week", weekStart.add(n, "week").format("YYYY-MM-DD"));

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  if (status) qs.set("status", status);
  if (staffId) qs.set("staff_id", staffId);

  const bookings = useQuery({
    queryKey: ["bookings", qs.toString()],
    queryFn: () => api<any>(`/api/bookings?${qs}`),
    enabled: view === "list",
    // при листании держим прошлую страницу, чтобы таблица не мигала пустотой
    placeholderData: keepPreviousData,
  });

  const hasFilters = Boolean(dateFrom || dateTo || status || staffId);

  return (
    <>
      <PageActions>
        <div className="segmented">
          <button aria-pressed={view === "list"} onClick={() => setParam("view", "")}>
            <LayoutList size={13} /> Список
          </button>
          <button aria-pressed={view === "week"} onClick={() => setParam("view", "week")}>
            <CalendarDays size={13} /> Неделя
          </button>
        </div>
        <Button variant="primary" size="sm" onClick={() => setNewPreset({})}>
          <Plus size={14} /> Новая запись
        </Button>
      </PageActions>

      <div className="filters">
        {view === "week" ? (
          <>
            <Button size="sm" icon onClick={() => shiftWeek(-1)} aria-label="Предыдущая неделя">
              <ChevronLeft size={14} />
            </Button>
            <Button size="sm" onClick={() => setParam("week", "")}>Текущая неделя</Button>
            <Button size="sm" icon onClick={() => shiftWeek(1)} aria-label="Следующая неделя">
              <ChevronRight size={14} />
            </Button>
            <span className="mono muted">
              {weekStart.format("D MMM")} — {weekStart.add(6, "day").format("D MMM YYYY")}
            </span>
          </>
        ) : (
          <>
            <input type="date" value={dateFrom} aria-label="Дата с"
                   onChange={(e) => setParam("date_from", e.target.value)} />
            <span className="dash">—</span>
            <input type="date" value={dateTo} aria-label="Дата по"
                   onChange={(e) => setParam("date_to", e.target.value)} />
            <select value={status} aria-label="Статус"
                    onChange={(e) => setParam("status", e.target.value)}>
              <option value="">Все статусы</option>
              {STATUS_OPTIONS.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
            </select>
          </>
        )}
        <select value={staffId} aria-label="Мастер"
                onChange={(e) => setParam("staff_id", e.target.value)}>
          <option value="">Все мастера</option>
          {(staff.data?.items ?? []).map((s: any) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        {view === "list" && hasFilters && (
          <button className="link-btn" onClick={() => setParams({}, { replace: true })}>
            Сбросить
          </button>
        )}
      </div>

      {view === "week" ? (
        <BookingsCalendar weekStart={weekStart} staffId={staffId}
                          onOpen={setOpenId} onCreate={setNewPreset} />
      ) : bookings.isError ? (
        <LoadError onRetry={() => bookings.refetch()} />
      ) : bookings.isLoading ? (
        <TableSkeleton rows={8} cols={6} />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Когда</th><th>Клиент</th><th>Услуга</th>
                  <th>Мастер</th><th>Каскад</th><th>Статус</th><th>Источник</th>
                </tr>
              </thead>
              <tbody>
                {(bookings.data?.items ?? []).map((b: any) => {
                  const cascade = cascadeFromStatus(b.status);
                  return (
                    <tr key={b.id} {...rowProps(() => setOpenId(b.id))}>
                      <td className="t-time nowrap">
                        {dayjs(b.starts_at).format("D MMM")}{" "}
                        <span className="strong">{dayjs(b.starts_at).format("HH:mm")}</span>
                      </td>
                      <td>{b.customer?.name ?? "—"}</td>
                      <td className="t-trunc">{b.service?.name}</td>
                      <td className="muted">{b.staff?.name ?? "любой"}</td>
                      <td>{cascade && <CascadeChain state={cascade} />}</td>
                      <td><Status value={b.status} label={b.status_display} /></td>
                      <td className="muted">{SOURCE_LABELS[b.source as string] ?? b.source}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!bookings.data?.items?.length && (
              <Empty
                text={hasFilters ? "Под фильтры ничего не подходит" : "Записей пока нет"}
                hint={hasFilters ? "Попробуйте расширить период или снять статус." : undefined}
                action={hasFilters
                  ? <Button size="sm" className="mt-2"
                            onClick={() => setParams({}, { replace: true })}>Сбросить фильтры</Button>
                  : <Button size="sm" variant="primary" className="mt-2"
                            onClick={() => setNewPreset({})}>Добавить запись</Button>}
              />
            )}
          </div>
          <Pager page={page} total={bookings.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}

      {newPreset && (
        <NewBookingModal preset={newPreset} onClose={() => setNewPreset(null)} />
      )}
      {openId !== null && <BookingModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

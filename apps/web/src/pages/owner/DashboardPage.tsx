import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { Badge, Empty, Spinner, money } from "../../components/ui";

function UpcomingTable({ items }: { items: any[] }) {
  if (!items.length) return <Empty text="Записей нет" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Время</th><th>Клиент</th><th>Услуга</th><th>Мастер</th><th>Статус</th></tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td><b>{dayjs(b.starts_at).format("HH:mm")}</b></td>
              <td>{b.customer?.name ?? "—"}</td>
              <td>{b.service?.name}</td>
              <td>{b.staff?.name ?? "любой"}</td>
              <td><Badge value={b.status} label={b.status_display} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const month = dayjs().format("YYYY-MM");
  const summary = useQuery({
    queryKey: ["summary", month],
    queryFn: () => api(`/api/dashboard/summary?month=${month}`),
  });
  const upcoming = useQuery({
    queryKey: ["upcoming"],
    queryFn: () => api("/api/dashboard/upcoming"),
  });

  if (summary.isLoading || upcoming.isLoading) return <Spinner />;
  const s = summary.data ?? {};
  const monthStart = dayjs().startOf("month").format("YYYY-MM-DD");
  const monthEnd = dayjs().endOf("month").format("YYYY-MM-DD");
  const go = (status?: string) =>
    navigate(`/bookings?date_from=${monthStart}&date_to=${monthEnd}` +
             (status ? `&status=${status}` : ""));

  return (
    <>
      <h1>Дашборд · {dayjs().format("MMMM YYYY")}</h1>
      <div className="metrics">
        <div className="metric" onClick={() => go()}>
          <div className="m-label">Записей за месяц</div>
          <div className="m-value">{s.bookings_total}</div>
        </div>
        <div className="metric" onClick={() => go("confirmed,done")}>
          <div className="m-label">Подтверждено</div>
          <div className="m-value">{s.confirmed}</div>
        </div>
        <div className="metric" onClick={() => go("no_show")}>
          <div className="m-label">Неявки</div>
          <div className="m-value">{s.no_show}</div>
        </div>
        <div className="metric metric-accent" onClick={() => navigate(`/reports/${month}`)}>
          <div className="m-label">Возвращено ≈</div>
          <div className="m-value">{money(s.returned_total ?? 0)}</div>
        </div>
      </div>

      <h2>Сегодня</h2>
      <UpcomingTable items={upcoming.data?.today ?? []} />
      <h2>Завтра</h2>
      <UpcomingTable items={upcoming.data?.tomorrow ?? []} />
    </>
  );
}

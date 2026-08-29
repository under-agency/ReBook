import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { Badge, Spinner, money } from "../../components/ui";

export default function ReportsPage() {
  const { month } = useParams();
  const navigate = useNavigate();
  const months = useQuery({ queryKey: ["report-months"], queryFn: () => api("/api/reports/months") });
  const current = month ?? months.data?.months?.[0] ?? dayjs().format("YYYY-MM");
  const report = useQuery({
    queryKey: ["report", current],
    enabled: Boolean(current),
    queryFn: () => api(`/api/reports/${current}`),
  });

  const r = report.data;

  return (
    <>
      <div className="page-head no-print">
        <h1>Отчёты</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <select value={current} onChange={(e) => navigate(`/reports/${e.target.value}`)}>
            {(months.data?.months ?? [current]).map((m: string) => (
              <option key={m} value={m}>{dayjs(m + "-01").format("MMMM YYYY")}</option>
            ))}
          </select>
          <button onClick={() => window.print()}>🖨 Печать / PDF</button>
        </div>
      </div>

      {report.isLoading || !r ? <Spinner /> : (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>
            {r.salon_name} — отчёт за {dayjs(r.month + "-01").format("MMMM YYYY")}
          </h2>
          <div className="metrics">
            <div className="metric"><div className="m-label">Записей</div>
              <div className="m-value">{r.bookings_total}</div></div>
            <div className="metric"><div className="m-label">Подтверждено после напоминания</div>
              <div className="m-value">{r.confirmed}</div></div>
            <div className="metric"><div className="m-label">Неявки</div>
              <div className="m-value">{r.no_show}</div></div>
            <div className="metric metric-accent"><div className="m-label">Возвращено ≈</div>
              <div className="m-value">{money(r.returned_total)}</div></div>
          </div>

          <h2>Как посчитано (формула открыта)</h2>
          <div className="table-wrap" style={{ marginBottom: 18 }}>
            <table>
              <tbody>
                <tr>
                  <td>Предотвращённые неявки</td>
                  <td className="hint">{r.confirmed} подтверждений × {r.no_show_rate} (коэффициент неявок) × {money(r.avg_check)} (средний чек)</td>
                  <td><b>{money(r.returned_prevented)}</b></td>
                </tr>
                <tr>
                  <td>Перепроданные окна (лист ожидания)</td>
                  <td className="hint">{r.waitlist_visits} визитов × {money(r.avg_check)}</td>
                  <td><b>{money(r.returned_waitlist)}</b></td>
                </tr>
                <tr>
                  <td>Возвращённые «спящие» клиенты</td>
                  <td className="hint">{r.reactivation_visits} визитов × {money(r.avg_check)}</td>
                  <td><b>{money(r.returned_reactivation)}</b></td>
                </tr>
                <tr>
                  <td><b>Итого возвращено</b></td><td />
                  <td><b>{money(r.returned_total)}</b></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="hint" style={{ marginBottom: 18 }}>
            Коэффициент неявок {r.no_show_rate} — консервативная оценка доли записей,
            которые были бы потеряны без напоминаний. Когда накопится ваша статистика
            за 2–3 месяца, подставим фактический показатель.
          </p>

          <h2>Записи по итогам месяца</h2>
          <div className="chips" style={{ marginBottom: 18 }}>
            <Badge value="done" label={`Состоялись: ${r.done}`} />
            <Badge value="no_show" label={`Неявки: ${r.no_show}`} />
            <Badge value="cancelled" label={`Отменены: ${r.cancelled}`} />
            <Badge value="rescheduled" label={`Перенесены: ${r.rescheduled}`} />
          </div>

          <h2>Сообщения и расходы</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Канал</th><th>Тип</th><th>Штук</th><th>Стоимость</th></tr></thead>
              <tbody>
                {r.messages.map((m: any, i: number) => (
                  <tr key={i}>
                    <td><Badge value={m.channel} label={m.channel.toUpperCase()} /></td>
                    <td>{m.kind}</td>
                    <td>{m.count}</td>
                    <td>{m.cost > 0 ? `${m.cost} ₽` : "бесплатно"}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={2}><b>Итого SMS: {r.sms_count} из {r.sms_limit} по лимиту</b></td>
                  <td />
                  <td><b>{r.sms_cost} ₽</b></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

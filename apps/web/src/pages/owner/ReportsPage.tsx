import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import { Printer } from "lucide-react";
import { api } from "../../api/client";
import { PageActions } from "../../components/Layout";
import {
  Button, LoadError, Status, TableSkeleton, Tag, money,
} from "../../components/ui";

/** Бэкенд отдаёт в отчёте сырой kind — в продающем документе он читаться не должен. */
const KIND_LABELS: Record<string, string> = {
  reminder_24h: "Напоминание за 24 ч", reminder_3h: "Напоминание за 3 ч",
  sms_chase: "SMS-догон", reactivation: "Реактивация", confirm: "Подтверждение",
  waitlist_offer: "Предложение окна", report: "Отчёт", faq: "Ответ на вопрос",
  test: "Тестовое",
};

export default function ReportsPage() {
  const { month } = useParams();
  const navigate = useNavigate();
  const months = useQuery({
    queryKey: ["report-months"],
    queryFn: () => api<{ months: string[] }>("/api/reports/months"),
  });
  const current = month ?? months.data?.months?.[0] ?? dayjs().format("YYYY-MM");
  const report = useQuery({
    queryKey: ["report", current],
    enabled: Boolean(current),
    queryFn: () => api<any>(`/api/reports/${current}`),
  });

  const r = report.data;

  return (
    <>
      <PageActions>
        <select value={current} aria-label="Месяц отчёта" style={{ width: "auto" }}
                onChange={(e) => navigate(`/reports/${e.target.value}`)}>
          {(months.data?.months ?? [current]).map((m: string) => (
            <option key={m} value={m}>{dayjs(m + "-01").format("MMMM YYYY")}</option>
          ))}
        </select>
        <Button size="sm" onClick={() => window.print()}>
          <Printer size={14} /> Печать / PDF
        </Button>
      </PageActions>

      {report.isError ? (
        <LoadError onRetry={() => report.refetch()} />
      ) : report.isLoading || !r ? (
        <TableSkeleton rows={6} cols={4} />
      ) : (
        <>
          <div className="section-head">
            <h2>{r.salon_name} · {dayjs(r.month + "-01").format("MMMM YYYY")}</h2>
          </div>

          <div className="metrics metrics-static">
            <div className="metric">
              <span className="m-label">Записей</span>
              <span className="m-value">{r.bookings_total}</span>
            </div>
            <div className="metric">
              <span className="m-label">Подтверждено</span>
              <span className="m-value">{r.confirmed}</span>
            </div>
            <div className="metric">
              <span className="m-label">Неявки</span>
              <span className="m-value">{r.no_show}</span>
            </div>
            <div className="metric metric-accent">
              <span className="m-label">Возвращено ≈</span>
              <span className="m-value">{money(r.returned_total)}</span>
            </div>
          </div>

          <div className="section-head">
            <h2>Как посчитано</h2>
            <span className="push">формула открыта — любую цифру можно проверить</span>
          </div>
          <div className="table-wrap mb-3">
            <table>
              <tbody>
                <tr>
                  <td>Предотвращённые неявки</td>
                  <td className="hint">
                    {r.confirmed} подтверждений × {r.no_show_rate} (коэффициент неявок)
                    {" "}× {money(r.avg_check)} (средний чек)
                  </td>
                  <td className="t-num strong">{money(r.returned_prevented)}</td>
                </tr>
                <tr>
                  <td>Перепроданные окна</td>
                  <td className="hint">{r.waitlist_visits} визитов × {money(r.avg_check)}</td>
                  <td className="t-num strong">{money(r.returned_waitlist)}</td>
                </tr>
                <tr>
                  <td>Возвращённые «спящие»</td>
                  <td className="hint">{r.reactivation_visits} визитов × {money(r.avg_check)}</td>
                  <td className="t-num strong">{money(r.returned_reactivation)}</td>
                </tr>
                <tr>
                  <td className="strong">Итого возвращено</td>
                  <td />
                  <td className="t-num strong">{money(r.returned_total)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="hint mb-4">
            Коэффициент неявок {r.no_show_rate} — консервативная оценка доли записей, которые
            были бы потеряны без напоминаний. Когда накопится ваша статистика за 2–3 месяца,
            подставим фактический показатель.
          </p>

          <div className="section-head"><h2>Записи по итогам месяца</h2></div>
          <div className="row row-wrap mb-4">
            <Status value="done" label={`Состоялись: ${r.done}`} />
            <Status value="no_show" label={`Неявки: ${r.no_show}`} />
            <Status value="cancelled" label={`Отменены: ${r.cancelled}`} />
            <Status value="rescheduled" label={`Перенесены: ${r.rescheduled}`} />
          </div>

          <div className="section-head"><h2>Сообщения и расходы</h2></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Канал</th><th>Тип</th>
                    <th className="t-num">Штук</th><th className="t-num">Стоимость</th></tr>
              </thead>
              <tbody>
                {r.messages.map((m: any, i: number) => (
                  <tr key={i}>
                    <td><Tag>{m.channel.toUpperCase()}</Tag></td>
                    <td className="muted">{KIND_LABELS[m.kind as string] ?? m.kind}</td>
                    <td className="t-num">{m.count}</td>
                    <td className="t-num muted">{m.cost > 0 ? `${m.cost} ₽` : "бесплатно"}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={2} className="strong">
                    Итого SMS: {r.sms_count} из {r.sms_limit} по лимиту
                  </td>
                  <td />
                  <td className="t-num strong">{r.sms_cost} ₽</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

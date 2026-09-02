import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "../../api/client";
import { PageActions } from "../../components/Layout";
import {
  Button, Empty, LoadError, Status, TableSkeleton, rowProps,
} from "../../components/ui";

export const SALON_STATUS_LABELS: Record<string, string> = {
  onboarding: "Внедрение", active: "Активен", grace: "Просрочка",
  paused: "Приостановлен", archived: "Архив",
};

export default function SalonsListPage() {
  const navigate = useNavigate();
  const salons = useQuery({
    queryKey: ["salons"],
    queryFn: () => api<any>("/api/admin/salons"),
  });

  return (
    <>
      <PageActions>
        <Button variant="primary" size="sm" onClick={() => navigate("/admin/salons/new")}>
          <Plus size={14} /> Новый салон
        </Button>
      </PageActions>

      <p className="hint mb-3">Проблемные салоны — сверху.</p>

      {salons.isError ? (
        <LoadError onRetry={() => salons.refetch()} />
      ) : salons.isLoading ? (
        <TableSkeleton rows={6} cols={6} />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Салон</th><th>Статус</th><th>Активность бота</th>
                  <th className="t-num">Ошибки 24 ч</th><th className="t-num">SMS / лимит</th>
                  <th>Следующий платёж</th></tr>
            </thead>
            <tbody>
              {(salons.data?.items ?? []).map((s: any) => (
                <tr key={s.id} {...rowProps(() => navigate(`/admin/salons/${s.id}`))}>
                  <td>
                    <div className="strong">{s.name}</div>
                    {s.niche && <div className="hint">{s.niche}</div>}
                  </td>
                  <td><Status value={s.status} label={SALON_STATUS_LABELS[s.status] ?? s.status} /></td>
                  <td className="t-time muted">
                    {s.health.last_activity
                      ? dayjs(s.health.last_activity).format("D MMM HH:mm")
                      : "—"}
                  </td>
                  <td className="t-num">
                    {s.health.errors_24h > 0
                      ? <span style={{ color: "var(--danger)" }} className="strong">
                          {s.health.errors_24h}
                        </span>
                      : <span className="dim">0</span>}
                  </td>
                  <td className="t-num">
                    <span className={s.health.sms_used >= s.sms_limit_month * 0.8
                      ? "strong" : "muted"}>
                      {s.health.sms_used}
                    </span>
                    <span className="dim"> / {s.sms_limit_month}</span>
                  </td>
                  <td className="t-time muted">
                    {s.next_payment_at ? dayjs(s.next_payment_at).format("D MMM YYYY") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!salons.data?.items?.length && (
            <Empty text="Салонов пока нет"
                   hint="Подключите первый салон — форма займёт 15 минут."
                   action={<Button size="sm" variant="primary" className="mt-2"
                                   onClick={() => navigate("/admin/salons/new")}>
                             Новый салон
                           </Button>} />
          )}
        </div>
      )}
    </>
  );
}

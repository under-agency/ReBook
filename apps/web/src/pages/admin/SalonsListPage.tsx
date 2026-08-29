import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { Badge, Empty, Spinner } from "../../components/ui";

export const SALON_STATUS_LABELS: Record<string, string> = {
  onboarding: "Внедрение", active: "Активен", grace: "Просрочка",
  paused: "Приостановлен", archived: "Архив",
};

export default function SalonsListPage() {
  const navigate = useNavigate();
  const salons = useQuery({ queryKey: ["salons"], queryFn: () => api("/api/admin/salons") });

  return (
    <>
      <div className="page-head">
        <h1>Салоны</h1>
        <button className="btn-primary" onClick={() => navigate("/admin/salons/new")}>
          + Новый салон
        </button>
      </div>
      {salons.isLoading ? <Spinner /> : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Салон</th><th>Статус</th><th>Активность бота</th>
                  <th>Ошибки 24 ч</th><th>SMS / лимит</th><th>След. платёж</th></tr>
            </thead>
            <tbody>
              {(salons.data?.items ?? []).map((s: any) => (
                <tr key={s.id} className="clickable"
                    onClick={() => navigate(`/admin/salons/${s.id}`)}>
                  <td><b>{s.name}</b><div className="hint">{s.niche ?? ""}</div></td>
                  <td><Badge value={s.status} label={SALON_STATUS_LABELS[s.status]} /></td>
                  <td>{s.health.last_activity
                        ? dayjs(s.health.last_activity).format("D MMM HH:mm") : "—"}</td>
                  <td>{s.health.errors_24h > 0
                        ? <Badge value="failed" label={String(s.health.errors_24h)} /> : "0"}</td>
                  <td>{s.health.sms_used} / {s.sms_limit_month}</td>
                  <td>{s.next_payment_at ? dayjs(s.next_payment_at).format("D MMM YYYY") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!salons.data?.items?.length && <Empty text="Салонов пока нет" />}
        </div>
      )}
    </>
  );
}

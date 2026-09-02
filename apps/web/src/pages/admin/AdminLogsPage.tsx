import { keepPreviousData, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../../api/client";
import AuditTable, { type AuditRow } from "../../components/AuditTable";
import {
  Empty, LoadError, Pager, Status, TableSkeleton, Tabs, Tag,
} from "../../components/ui";

const DELIVERY_LABELS: Record<string, string> = {
  sent: "доставлено", stub: "заглушка", failed: "ошибка",
};

function MessagesLog() {
  const [page, setPage] = useState(1);
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (channel) qs.set("channel", channel);
  if (status) qs.set("delivery_status", status);

  const data = useQuery({
    queryKey: ["admin-messages", qs.toString()],
    queryFn: () => api<any>(`/api/admin/messages?${qs}`),
    placeholderData: keepPreviousData,
  });

  if (data.isError) return <LoadError onRetry={() => data.refetch()} />;

  return (
    <>
      <div className="filters">
        <select value={channel} aria-label="Канал"
                onChange={(e) => { setChannel(e.target.value); setPage(1); }}>
          <option value="">Все каналы</option>
          <option value="tg">Telegram</option><option value="sms">SMS</option>
        </select>
        <select value={status} aria-label="Статус доставки"
                onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Все статусы</option>
          <option value="sent">Доставлено</option>
          <option value="stub">Заглушка</option>
          <option value="failed">Ошибка</option>
        </select>
      </div>
      {data.isLoading ? <TableSkeleton rows={8} cols={6} /> : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Когда</th><th>Салон</th><th>Клиент</th><th>Тип</th>
                    <th>Канал</th><th>Доставка</th><th className="t-num">₽</th></tr>
              </thead>
              <tbody>
                {(data.data?.items ?? []).map((m: any) => (
                  <tr key={m.id}>
                    <td className="t-time nowrap">{dayjs(m.sent_at).format("D MMM HH:mm")}</td>
                    <td className="mono">#{m.salon_id}</td>
                    <td>{m.customer?.name ?? "—"}</td>
                    <td className="muted">{m.kind_display}</td>
                    <td><Tag>{m.channel.toUpperCase()}</Tag></td>
                    <td>
                      <Status value={m.delivery_status ?? "sent"}
                              label={DELIVERY_LABELS[m.delivery_status as string]
                                     ?? m.delivery_status} />
                    </td>
                    <td className="t-num muted">{m.cost > 0 ? m.cost : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.data?.items?.length && (
              <Empty text="Сообщений не найдено"
                     hint="Здесь виден трафик всех салонов — удобно ловить всплески расхода SMS." />
            )}
          </div>
          <Pager page={page} total={data.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
    </>
  );
}

function AuditLog() {
  const [page, setPage] = useState(1);
  const data = useQuery({
    queryKey: ["admin-audit", page],
    queryFn: () => api<{ items: AuditRow[]; total: number }>(
      `/api/admin/audit?page=${page}&page_size=50`,
    ),
    placeholderData: keepPreviousData,
  });

  if (data.isError) return <LoadError onRetry={() => data.refetch()} />;
  if (data.isLoading) return <TableSkeleton rows={8} cols={6} />;

  return (
    <>
      <AuditTable rows={data.data?.items ?? []} withSalon
                  emptyText="Действий пока не было" />
      <Pager page={page} total={data.data?.total ?? 0} pageSize={50} onPage={setPage} />
    </>
  );
}

export default function AdminLogsPage() {
  const [tab, setTab] = useState("messages");
  return (
    <>
      <Tabs active={tab} onChange={setTab}
            tabs={[["messages", "Сообщения"], ["audit", "Действия"]]} />
      {tab === "messages" ? <MessagesLog /> : <AuditLog />}
    </>
  );
}

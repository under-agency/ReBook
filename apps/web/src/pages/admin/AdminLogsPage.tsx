import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../../api/client";
import { Badge, Empty, Pager, Spinner, Tabs } from "../../components/ui";

function MessagesLog() {
  const [page, setPage] = useState(1);
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (channel) qs.set("channel", channel);
  if (status) qs.set("delivery_status", status);
  const data = useQuery({
    queryKey: ["admin-messages", qs.toString()],
    queryFn: () => api(`/api/admin/messages?${qs}`),
  });
  return (
    <>
      <div className="filters">
        <select value={channel} onChange={(e) => { setChannel(e.target.value); setPage(1); }}>
          <option value="">Все каналы</option>
          <option value="tg">Telegram</option><option value="sms">SMS</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Все статусы</option>
          <option value="sent">Доставлено</option>
          <option value="stub">Заглушка</option>
          <option value="failed">Ошибка</option>
        </select>
      </div>
      {data.isLoading ? <Spinner /> : (
        <>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Когда</th><th>Салон</th><th>Клиент</th><th>Тип</th>
                         <th>Канал</th><th>Статус</th><th>₽</th></tr></thead>
              <tbody>
                {(data.data?.items ?? []).map((m: any) => (
                  <tr key={m.id}>
                    <td>{dayjs(m.sent_at).format("D MMM HH:mm")}</td>
                    <td>#{m.salon_id}</td>
                    <td>{m.customer?.name ?? "—"}</td>
                    <td>{m.kind_display}</td>
                    <td><Badge value={m.channel} label={m.channel.toUpperCase()} /></td>
                    <td><Badge value={m.delivery_status ?? "sent"}
                               label={m.delivery_status ?? ""} /></td>
                    <td>{m.cost > 0 ? m.cost : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.data?.items?.length && <Empty />}
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
    queryFn: () => api(`/api/admin/audit?page=${page}&page_size=50`),
  });
  return data.isLoading ? <Spinner /> : (
    <>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Когда</th><th>Салон</th><th>Кто</th><th>Действие</th><th>Объект</th></tr></thead>
          <tbody>
            {(data.data?.items ?? []).map((a: any) => (
              <tr key={a.id}>
                <td>{dayjs(a.created_at).format("D MMM HH:mm")}</td>
                <td>{a.salon_id ? `#${a.salon_id}` : "—"}</td>
                <td>{a.user_email ?? "система"}</td>
                <td>{a.action}{a.is_support && <> <Badge value="stub" label="поддержка" /></>}</td>
                <td>{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.data?.items?.length && <Empty />}
      </div>
      <Pager page={page} total={data.data?.total ?? 0} pageSize={50} onPage={setPage} />
    </>
  );
}

export default function AdminLogsPage() {
  const [tab, setTab] = useState("messages");
  return (
    <>
      <div className="page-head"><h1>Журналы</h1></div>
      <Tabs active={tab} onChange={setTab}
            tabs={[["messages", "Сообщения"], ["audit", "Аудит"]]} />
      {tab === "messages" ? <MessagesLog /> : <AuditLog />}
    </>
  );
}

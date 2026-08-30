import { keepPreviousData, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api } from "../../api/client";
import { Badge, Empty, Pager, Spinner } from "../../components/ui";

const KINDS: [string, string][] = [
  ["reminder_24h", "Напоминание 24 ч"], ["reminder_3h", "Напоминание 3 ч"],
  ["sms_chase", "SMS-догон"], ["confirm", "Подтверждение"],
  ["reactivation", "Реактивация"], ["waitlist_offer", "Предложение окна"],
];

export default function MessagesPage() {
  const [channel, setChannel] = useState("");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);

  const stats = useQuery({ queryKey: ["msg-stats"], queryFn: () => api("/api/messages/stats") });
  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (channel) qs.set("channel", channel);
  if (kind) qs.set("kind", kind);
  const messages = useQuery({
    queryKey: ["messages", qs.toString()],
    queryFn: () => api(`/api/messages?${qs}`),
    placeholderData: keepPreviousData,
  });

  const s = stats.data;
  const smsPct = s ? Math.min(100, Math.round((s.sms_used / s.sms_limit) * 100)) : 0;

  return (
    <>
      <div className="page-head"><h1>Сообщения</h1></div>
      {s && (
        <div className="card" style={{ maxWidth: 420 }}>
          <b>SMS за {dayjs(s.month + "-01").format("MMMM")}: {s.sms_used} из {s.sms_limit}</b>
          <div className={"progress" + (smsPct >= 80 ? " progress-danger" : "")}>
            <div style={{ width: `${smsPct}%` }} />
          </div>
          <span className="hint">Потрачено {s.sms_cost} ₽ · Telegram — бесплатно
            ({s.by_channel?.tg?.count ?? 0} шт.)</span>
        </div>
      )}
      <div className="filters">
        <select value={channel} onChange={(e) => { setChannel(e.target.value); setPage(1); }}>
          <option value="">Все каналы</option>
          <option value="tg">Telegram</option>
          <option value="sms">SMS</option>
        </select>
        <select value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}>
          <option value="">Все типы</option>
          {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </div>
      {messages.isLoading ? <Spinner /> : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Когда</th><th>Клиент</th><th>Тип</th><th>Канал</th>
                    <th>Статус</th><th>Стоимость</th><th>Текст</th></tr>
              </thead>
              <tbody>
                {(messages.data?.items ?? []).map((m: any) => (
                  <tr key={m.id}>
                    <td>{dayjs(m.sent_at).format("D MMM HH:mm")}</td>
                    <td>{m.customer?.name ?? "—"}</td>
                    <td>{m.kind_display}</td>
                    <td><Badge value={m.channel} label={m.channel.toUpperCase()} /></td>
                    <td><Badge value={m.delivery_status ?? "sent"}
                               label={{ sent: "доставлено", stub: "заглушка", failed: "ошибка" }[m.delivery_status as string] ?? m.delivery_status} /></td>
                    <td>{m.cost > 0 ? `${m.cost} ₽` : "—"}</td>
                    <td style={{ maxWidth: 340, whiteSpace: "nowrap", overflow: "hidden",
                                 textOverflow: "ellipsis" }} title={m.text}>{m.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!messages.data?.items?.length && <Empty text="Сообщений не найдено" />}
          </div>
          <Pager page={page} total={messages.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
    </>
  );
}

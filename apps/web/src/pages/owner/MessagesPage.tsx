import { keepPreviousData, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import {
  Empty, LoadError, Pager, Skeleton, Status, TableSkeleton, Tag,
} from "../../components/ui";

const KINDS: [string, string][] = [
  ["reminder_24h", "Напоминание 24 ч"], ["reminder_3h", "Напоминание 3 ч"],
  ["sms_chase", "SMS-догон"], ["confirm", "Подтверждение"],
  ["reactivation", "Реактивация"], ["waitlist_offer", "Предложение окна"],
];

const DELIVERY_LABELS: Record<string, string> = {
  sent: "доставлено", stub: "заглушка", failed: "ошибка",
};

export default function MessagesPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);

  const channel = params.get("channel") ?? "";
  const kind = params.get("kind") ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  const stats = useQuery({ queryKey: ["msg-stats"], queryFn: () => api<any>("/api/messages/stats") });

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (channel) qs.set("channel", channel);
  if (kind) qs.set("kind", kind);
  const messages = useQuery({
    queryKey: ["messages", qs.toString()],
    queryFn: () => api<any>(`/api/messages?${qs}`),
    placeholderData: keepPreviousData,
  });

  const s = stats.data;
  const smsPct = s?.sms_limit ? Math.min(100, Math.round((s.sms_used / s.sms_limit) * 100)) : 0;

  return (
    <>
      <div className="card narrow">
        {stats.isLoading || !s ? (
          <div className="stack"><Skeleton w="60%" h={13} /><Skeleton w="100%" h={4} /></div>
        ) : (
          <>
            <div className="row mb-2">
              <span className="strong">SMS за {dayjs(s.month + "-01").format("MMMM")}</span>
              <span className="mono push">
                {s.sms_used} / {s.sms_limit}
              </span>
            </div>
            <div className={"progress" + (smsPct >= 80 ? " progress-danger" : "")}>
              <div style={{ width: `${smsPct}%` }} />
            </div>
            <span className="hint">
              Потрачено <span className="mono">{s.sms_cost} ₽</span>. Telegram бесплатен —{" "}
              <span className="mono">{s.by_channel?.tg?.count ?? 0}</span> сообщений за месяц.
            </span>
          </>
        )}
      </div>

      <div className="filters">
        <select value={channel} aria-label="Канал"
                onChange={(e) => setParam("channel", e.target.value)}>
          <option value="">Все каналы</option>
          <option value="tg">Telegram</option>
          <option value="sms">SMS</option>
        </select>
        <select value={kind} aria-label="Тип сообщения"
                onChange={(e) => setParam("kind", e.target.value)}>
          <option value="">Все типы</option>
          {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        {(channel || kind) && (
          <button className="link-btn" onClick={() => setParams({}, { replace: true })}>
            Сбросить
          </button>
        )}
      </div>

      {messages.isError ? (
        <LoadError onRetry={() => messages.refetch()} />
      ) : messages.isLoading ? (
        <TableSkeleton rows={8} cols={6} />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Когда</th><th>Клиент</th><th>Тип</th><th>Канал</th>
                    <th>Доставка</th><th className="t-num">Стоимость</th><th>Текст</th></tr>
              </thead>
              <tbody>
                {(messages.data?.items ?? []).map((m: any) => (
                  <tr key={m.id}>
                    <td className="t-time nowrap">{dayjs(m.sent_at).format("D MMM HH:mm")}</td>
                    <td>{m.customer?.name ?? "—"}</td>
                    <td className="muted">{m.kind_display}</td>
                    <td><Tag>{m.channel.toUpperCase()}</Tag></td>
                    <td>
                      <Status value={m.delivery_status ?? "sent"}
                              label={DELIVERY_LABELS[m.delivery_status as string] ?? m.delivery_status} />
                    </td>
                    <td className="t-num muted">{m.cost > 0 ? `${m.cost} ₽` : "—"}</td>
                    <td className="t-trunc muted" title={m.text}>{m.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!messages.data?.items?.length && (
              <Empty text="Сообщений не найдено"
                     hint="Здесь виден каждый отправленный бот-месседж и SMS с его стоимостью." />
            )}
          </div>
          <Pager page={page} total={messages.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
    </>
  );
}

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BellOff, Bell } from "lucide-react";
import { api, errorText } from "../../api/client";
import { useToast } from "../../components/toast";
import {
  Button, Empty, LoadError, Modal, Pager, Skeleton, Status, Tag, TableSkeleton, rowProps,
} from "../../components/ui";

const STATUS_LABELS: Record<string, string> = {
  active: "Активный", sleeping: "Спящий", lost: "Потерянный", excluded: "Исключён",
};

const channels = (c: { has_tg?: boolean; has_max?: boolean }) =>
  [c.has_tg && "Telegram", c.has_max && "MAX"].filter(Boolean) as string[];

function CustomerModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const customer = useQuery({
    queryKey: ["customer", id],
    queryFn: () => api<any>(`/api/customers/${id}`),
  });
  const c = customer.data;

  const toggleDnd = async () => {
    setBusy(true);
    try {
      await api(`/api/customers/${id}`, {
        method: "PATCH", body: { do_not_disturb: !c.do_not_disturb },
      });
      qc.invalidateQueries({ queryKey: ["customer", id] });
      qc.invalidateQueries({ queryKey: ["customers"] });
      toast.ok(c.do_not_disturb
        ? "Клиент снова получает напоминания"
        : "Клиент исключён из рассылок");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={c?.name ?? "Клиент"} onClose={onClose} wide>
      {customer.isError ? (
        <LoadError onRetry={() => customer.refetch()} />
      ) : customer.isLoading || !c ? (
        <div className="stack">
          <Skeleton w="55%" h={14} /><Skeleton w="75%" h={14} /><Skeleton w="40%" h={14} />
        </div>
      ) : (
        <>
          <dl className="kv">
            <dt>Телефон</dt><dd className="mono">{c.phone ?? "—"}</dd>
            <dt>Каналы</dt>
            <dd>
              {channels(c).length
                ? channels(c).map((ch) => <Tag key={ch}>{ch}</Tag>)
                : <span className="muted">только SMS</span>}
            </dd>
            <dt>Последний визит</dt>
            <dd>{c.last_visit_at ? dayjs(c.last_visit_at).format("D MMMM YYYY") : "—"}</dd>
            <dt>Последняя услуга</dt><dd>{c.last_service ?? "—"}</dd>
            <dt>Статус</dt>
            <dd><Status value={c.status} label={STATUS_LABELS[c.status] ?? c.status} /></dd>
          </dl>

          <div className="mb-4">
            <Button variant={c.do_not_disturb ? "default" : "danger"}
                    disabled={busy} onClick={toggleDnd}>
              {c.do_not_disturb
                ? <><Bell size={14} /> Вернуть в рассылки</>
                : <><BellOff size={14} /> Исключить из рассылок</>}
            </Button>
          </div>

          <h3 className="mb-2">История визитов</h3>
          {c.visits?.length ? (
            <div className="table-wrap mb-4">
              <table>
                <thead><tr><th>Когда</th><th>Услуга</th><th>Мастер</th><th>Статус</th></tr></thead>
                <tbody>
                  {c.visits.map((b: any) => (
                    <tr key={b.id}>
                      <td className="t-time nowrap">
                        {dayjs(b.starts_at).format("D MMM YYYY HH:mm")}
                      </td>
                      <td>{b.service?.name}</td>
                      <td className="muted">{b.staff?.name ?? "любой"}</td>
                      <td><Status value={b.status} label={b.status_display} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty text="Визитов не было" />}

          <h3 className="mb-2">Переписка и рассылки</h3>
          {c.messages?.length ? (
            <div className="msg-history">
              {c.messages.map((m: any) => (
                <div className="msg-item" key={m.id}>
                  <div className="msg-meta">
                    <span className="mono">{dayjs(m.sent_at).format("D MMM YYYY HH:mm")}</span>
                    <span>{m.kind_display}</span>
                    <Tag>{m.channel.toUpperCase()}</Tag>
                    {m.cost > 0 && <span className="mono">{m.cost} ₽</span>}
                  </div>
                  {m.text}
                </div>
              ))}
            </div>
          ) : (
            <Empty text="Сообщений не было"
                   hint="Здесь появится вся переписка бота — пригодится при споре «мне ничего не приходило»." />
          )}
        </>
      )}
    </Modal>
  );
}

export default function CustomersPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<number | null>(null);

  const status = params.get("status") ?? "";
  const urlQ = params.get("q") ?? "";
  const [text, setText] = useState(urlQ);

  // Поиск бил запросом на каждое нажатие — придерживаем на 300 мс
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (text === urlQ) return;
      const next = new URLSearchParams(params);
      if (text) next.set("q", text); else next.delete("q");
      setParams(next, { replace: true });
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps

  const setStatus = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("status", value); else next.delete("status");
    setParams(next, { replace: true });
    setPage(1);
  };

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (urlQ) qs.set("q", urlQ);
  if (status) qs.set("status", status);

  const customers = useQuery({
    queryKey: ["customers", qs.toString()],
    queryFn: () => api<any>(`/api/customers?${qs}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="filters">
        <input placeholder="Имя или телефон" value={text} aria-label="Поиск клиентов"
               onChange={(e) => setText(e.target.value)} style={{ width: 220 }} />
        <div className="chips">
          <button className={"chip" + (status === "" ? " chip-active" : "")}
                  onClick={() => setStatus("")}>Все</button>
          {Object.entries(STATUS_LABELS).map(([key, label]) => (
            <button key={key} className={"chip" + (status === key ? " chip-active" : "")}
                    onClick={() => setStatus(key)}>{label}</button>
          ))}
        </div>
        {status === "sleeping" && (
          <span className="hint">Кандидаты на реактивацию — цикл услуги истёк</span>
        )}
      </div>

      {customers.isError ? (
        <LoadError onRetry={() => customers.refetch()} />
      ) : customers.isLoading ? (
        <TableSkeleton rows={8} cols={6} />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Имя</th><th>Телефон</th><th>Каналы</th>
                    <th>Последний визит</th><th>Последняя услуга</th><th>Статус</th></tr>
              </thead>
              <tbody>
                {(customers.data?.items ?? []).map((c: any) => (
                  <tr key={c.id} {...rowProps(() => setOpenId(c.id))}>
                    <td className="strong">{c.name ?? "—"}</td>
                    <td className="mono muted">{c.phone ?? "—"}</td>
                    <td className="muted">
                      {[c.has_tg && "TG", c.has_max && "MAX"].filter(Boolean).join(", ") || "SMS"}
                    </td>
                    <td className="t-time">
                      {c.last_visit_at ? dayjs(c.last_visit_at).format("D MMM YYYY") : "—"}
                    </td>
                    <td className="t-trunc muted">{c.last_service ?? "—"}</td>
                    <td><Status value={c.status} label={STATUS_LABELS[c.status] ?? c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!customers.data?.items?.length && (
              <Empty text="Клиентов не найдено"
                     hint={urlQ || status
                       ? "Попробуйте изменить запрос или снять фильтр."
                       : "Клиенты появятся после первой записи через бота."} />
            )}
          </div>
          <Pager page={page} total={customers.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
      {openId !== null && <CustomerModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

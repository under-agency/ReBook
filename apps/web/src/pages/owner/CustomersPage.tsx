import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { api, errorText } from "../../api/client";
import { Badge, Empty, Field, Modal, Pager, Spinner } from "../../components/ui";

const STATUS_LABELS: Record<string, string> = {
  active: "Активный", sleeping: "Спящий", lost: "Потерянный", excluded: "Исключён",
};

function CustomerModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const customer = useQuery({
    queryKey: ["customer", id],
    queryFn: () => api(`/api/customers/${id}`),
  });
  const c = customer.data;

  const toggleDnd = async () => {
    setError("");
    try {
      await api(`/api/customers/${id}`, {
        method: "PATCH", body: { do_not_disturb: !c.do_not_disturb },
      });
      qc.invalidateQueries({ queryKey: ["customer", id] });
      qc.invalidateQueries({ queryKey: ["customers"] });
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <Modal title={c?.name ?? "Клиент"} onClose={onClose} wide>
      {customer.isLoading || !c ? <Spinner /> : (
        <>
          <dl className="kv">
            <dt>Телефон</dt><dd>{c.phone ?? "—"}</dd>
            <dt>Каналы</dt><dd>{[c.has_tg && "Telegram", c.has_max && "MAX"].filter(Boolean).join(", ") || "только SMS"}</dd>
            <dt>Последний визит</dt><dd>{c.last_visit_at ? dayjs(c.last_visit_at).format("D MMMM YYYY") : "—"}</dd>
            <dt>Последняя услуга</dt><dd>{c.last_service ?? "—"}</dd>
            <dt>Статус</dt><dd><Badge value={c.status} label={STATUS_LABELS[c.status]} /></dd>
          </dl>
          <div style={{ marginBottom: 16 }}>
            <button className={c.do_not_disturb ? "" : "btn-danger"} onClick={toggleDnd}>
              {c.do_not_disturb ? "Вернуть в рассылки" : "🔕 Исключить из рассылок"}
            </button>
          </div>
          {error && <div className="error-text">{error}</div>}

          <h3 style={{ margin: "10px 0 8px" }}>История визитов</h3>
          {c.visits?.length ? (
            <div className="table-wrap" style={{ marginBottom: 16 }}>
              <table>
                <thead><tr><th>Дата</th><th>Услуга</th><th>Мастер</th><th>Статус</th></tr></thead>
                <tbody>
                  {c.visits.map((b: any) => (
                    <tr key={b.id}>
                      <td>{dayjs(b.starts_at).format("D MMM YYYY HH:mm")}</td>
                      <td>{b.service?.name}</td>
                      <td>{b.staff?.name ?? "любой"}</td>
                      <td><Badge value={b.status} label={b.status_display} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty text="Визитов не было" />}

          <h3 style={{ margin: "10px 0 8px" }}>Переписка и рассылки</h3>
          {c.messages?.length ? (
            <div className="msg-history">
              {c.messages.map((m: any) => (
                <div className="msg-item" key={m.id}>
                  <div className="msg-meta">
                    {dayjs(m.sent_at).format("D MMM YYYY HH:mm")} · {m.kind_display} ·
                    <Badge value={m.channel} label={m.channel.toUpperCase()} />
                    {m.cost > 0 && <span>{m.cost} ₽</span>}
                  </div>
                  {m.text}
                </div>
              ))}
            </div>
          ) : <Empty text="Сообщений не было" />}
        </>
      )}
    </Modal>
  );
}

export default function CustomersPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<number | null>(null);

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (q) qs.set("q", q);
  if (status) qs.set("status", status);
  const customers = useQuery({
    queryKey: ["customers", qs.toString()],
    queryFn: () => api(`/api/customers?${qs}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="page-head"><h1>Клиенты</h1></div>
      <div className="filters">
        <input placeholder="Поиск: имя или телефон" value={q}
               onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ width: 240 }} />
        <div className="chips">
          <button className={"chip" + (status === "" ? " chip-active" : "")}
                  onClick={() => { setStatus(""); setPage(1); }}>Все</button>
          {Object.entries(STATUS_LABELS).map(([key, label]) => (
            <button key={key} className={"chip" + (status === key ? " chip-active" : "")}
                    onClick={() => { setStatus(key); setPage(1); }}>{label}</button>
          ))}
        </div>
      </div>
      {customers.isLoading ? <Spinner /> : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Имя</th><th>Телефон</th><th>Каналы</th>
                    <th>Последний визит</th><th>Последняя услуга</th><th>Статус</th></tr>
              </thead>
              <tbody>
                {(customers.data?.items ?? []).map((c: any) => (
                  <tr key={c.id} className="clickable" onClick={() => setOpenId(c.id)}>
                    <td><b>{c.name ?? "—"}</b></td>
                    <td>{c.phone ?? "—"}</td>
                    <td>{[c.has_tg && "TG", c.has_max && "MAX"].filter(Boolean).join(", ") || "SMS"}</td>
                    <td>{c.last_visit_at ? dayjs(c.last_visit_at).format("D MMM YYYY") : "—"}</td>
                    <td>{c.last_service ?? "—"}</td>
                    <td><Badge value={c.status} label={STATUS_LABELS[c.status]} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!customers.data?.items?.length && <Empty text="Клиентов не найдено" />}
          </div>
          <Pager page={page} total={customers.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}
      {openId !== null && <CustomerModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

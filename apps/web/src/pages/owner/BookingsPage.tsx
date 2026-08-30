import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorText } from "../../api/client";
import {
  Badge, Empty, Field, Modal, Pager, Spinner, money,
} from "../../components/ui";

const STATUS_OPTIONS: [string, string][] = [
  ["new", "Новая"], ["reminded_24h", "Ждём ответ"], ["reminded_sms", "Ждём ответ (SMS)"],
  ["confirmed", "Придёт"], ["done", "Состоялась"], ["rescheduled", "Перенесена"],
  ["cancelled", "Отменена"], ["no_show", "Неявка"],
];
const MANUAL_STATUSES: [string, string][] = [
  ["confirmed", "Придёт"], ["done", "Состоялась"],
  ["cancelled", "Отменена"], ["no_show", "Неявка"], ["new", "Новая"],
];

function SlotPicker({
  serviceId, staffId, date, value, onChange,
}: { serviceId: number | ""; staffId: number | ""; date: string;
     value: string; onChange: (iso: string) => void }) {
  const slots = useQuery({
    queryKey: ["slots", serviceId, staffId, date],
    enabled: Boolean(serviceId && date),
    queryFn: () => api(`/api/bookings/free-slots?service_id=${serviceId}&date=${date}` +
                       (staffId ? `&staff_id=${staffId}` : "")),
  });
  if (!serviceId || !date) return <div className="hint">Выберите услугу и день</div>;
  if (slots.isLoading) return <Spinner />;
  const items = slots.data?.slots ?? [];
  if (!items.length) return <div className="hint">Свободных окон нет</div>;
  return (
    <div className="slot-grid">
      {items.map((s: any) => (
        <button type="button" key={s.starts_at}
                className={"slot" + (value === s.starts_at ? " slot-active" : "")}
                onClick={() => onChange(s.starts_at)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}

function NewBookingModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const services = useQuery({ queryKey: ["services"], queryFn: () => api("/api/settings/services") });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api("/api/settings/staff") });
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerId, setCustomerId] = useState<number | "">("");
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [serviceId, setServiceId] = useState<number | "">("");
  const [staffId, setStaffId] = useState<number | "">("");
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [slot, setSlot] = useState("");
  const [note, setNote] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const found = useQuery({
    queryKey: ["customer-search", customerQuery],
    enabled: customerQuery.length >= 2,
    queryFn: () => api(`/api/customers?q=${encodeURIComponent(customerQuery)}&page_size=8`),
  });

  const submit = async (force = false) => {
    setError("");
    setWarnings([]);
    if (!serviceId || !slot || (!customerId && !newName)) {
      setError("Заполните клиента, услугу и время");
      return;
    }
    setBusy(true);
    try {
      await api("/api/bookings", {
        method: "POST",
        body: {
          customer_id: customerId || null,
          new_customer: customerId ? null : { name: newName, phone: newPhone || null },
          service_id: serviceId,
          staff_id: staffId || null,
          starts_at: slot,
          note: note || null,
          force,
        },
      });
      qc.invalidateQueries({ queryKey: ["bookings"] });
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      onClose();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.warnings) setWarnings(e.detail.warnings);
      else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Добавить запись" onClose={onClose}>
      <Field label="Клиент — поиск по имени или телефону">
        <input value={customerQuery} placeholder="Начните вводить…"
               onChange={(e) => { setCustomerQuery(e.target.value); setCustomerId(""); }} />
      </Field>
      {customerQuery.length >= 2 && !customerId && (
        <div className="chips" style={{ marginBottom: 12 }}>
          {(found.data?.items ?? []).map((c: any) => (
            <button type="button" key={c.id} className="chip"
                    onClick={() => { setCustomerId(c.id); setCustomerQuery(`${c.name ?? ""} ${c.phone ?? ""}`.trim()); }}>
              {c.name} {c.phone}
            </button>
          ))}
          {found.data && !found.data.items.length && <span className="hint">Не найдено — создадим нового</span>}
        </div>
      )}
      {!customerId && (
        <div className="form-row">
          <Field label="Имя нового клиента">
            <input value={newName} onChange={(e) => setNewName(e.target.value)} />
          </Field>
          <Field label="Телефон">
            <input value={newPhone} placeholder="+7 900 000-00-00"
                   onChange={(e) => setNewPhone(e.target.value)} />
          </Field>
        </div>
      )}
      <div className="form-row">
        <Field label="Услуга">
          <select value={serviceId} onChange={(e) => { setServiceId(Number(e.target.value) || ""); setSlot(""); }}>
            <option value="">—</option>
            {(services.data?.items ?? []).filter((s: any) => s.is_active).map((s: any) => (
              <option key={s.id} value={s.id}>{s.name} · {money(s.price)}</option>
            ))}
          </select>
        </Field>
        <Field label="Мастер">
          <select value={staffId} onChange={(e) => { setStaffId(Number(e.target.value) || ""); setSlot(""); }}>
            <option value="">Любой</option>
            {(staff.data?.items ?? []).filter((s: any) => s.is_active).map((s: any) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </Field>
        <Field label="День">
          <input type="date" value={date}
                 onChange={(e) => { setDate(e.target.value); setSlot(""); }} />
        </Field>
      </div>
      <Field label="Время">
        <SlotPicker serviceId={serviceId} staffId={staffId} date={date}
                    value={slot} onChange={setSlot} />
      </Field>
      <Field label="Комментарий">
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {warnings.length > 0 && (
        <div className="error-text">
          ⚠ {warnings.join("; ")}
          <div style={{ marginTop: 8 }}>
            <button className="btn-danger" disabled={busy} onClick={() => submit(true)}>
              Всё равно записать
            </button>
          </div>
        </div>
      )}
      {error && <div className="error-text">{error}</div>}
      <button className="btn-primary" disabled={busy} onClick={() => submit(false)}>
        {busy ? "Сохраняем…" : "Записать"}
      </button>
    </Modal>
  );
}

function BookingModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const [resched, setResched] = useState(false);
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [slot, setSlot] = useState("");
  const booking = useQuery({
    queryKey: ["booking", id],
    queryFn: () => api(`/api/bookings/${id}`),
  });

  const b = booking.data;
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["booking", id] });
    qc.invalidateQueries({ queryKey: ["bookings"] });
    qc.invalidateQueries({ queryKey: ["upcoming"] });
  };

  const setStatus = async (status: string) => {
    setError("");
    try {
      await api(`/api/bookings/${id}`, { method: "PATCH", body: { status } });
      refresh();
    } catch (e) {
      setError(errorText(e));
    }
  };

  const doResched = async (force = false) => {
    setError("");
    try {
      await api(`/api/bookings/${id}/reschedule`, {
        method: "POST", body: { starts_at: slot, staff_id: b?.staff?.id ?? null, force },
      });
      refresh();
      onClose();
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <Modal title={`Запись #${id}`} onClose={onClose} wide>
      {booking.isLoading || !b ? <Spinner /> : (
        <>
          <dl className="kv">
            <dt>Клиент</dt><dd>{b.customer?.name} · {b.customer?.phone ?? "без телефона"}
              {b.customer?.has_tg ? " · TG ✓" : ""}</dd>
            <dt>Услуга</dt><dd>{b.service?.name} · {money(b.service?.price ?? 0)}</dd>
            <dt>Мастер</dt><dd>{b.staff?.name ?? "любой"}</dd>
            <dt>Когда</dt><dd>{dayjs(b.starts_at).format("D MMMM YYYY, HH:mm")} · {b.duration_min} мин</dd>
            <dt>Статус</dt><dd><Badge value={b.status} label={b.status_display} /></dd>
            <dt>Источник</dt><dd>{{ bot: "бот", manual: "вручную", yclients: "YCLIENTS" }[b.source as string] ?? b.source}</dd>
            {b.note && (<><dt>Комментарий</dt><dd>{b.note}</dd></>)}
          </dl>

          <div className="chips" style={{ marginBottom: 14 }}>
            {MANUAL_STATUSES.filter(([s]) => s !== b.status).map(([s, label]) => (
              <button key={s} className="chip" onClick={() => setStatus(s)}>→ {label}</button>
            ))}
            <button className="chip" onClick={() => setResched(!resched)}>🔄 Перенести</button>
          </div>

          {resched && (
            <div className="card">
              <div className="form-row">
                <Field label="Новый день">
                  <input type="date" value={date}
                         onChange={(e) => { setDate(e.target.value); setSlot(""); }} />
                </Field>
              </div>
              <SlotPicker serviceId={b.service.id} staffId={b.staff?.id ?? ""}
                          date={date} value={slot} onChange={setSlot} />
              <div style={{ marginTop: 12 }}>
                <button className="btn-primary" disabled={!slot} onClick={() => doResched(false)}>
                  Перенести
                </button>
              </div>
            </div>
          )}
          {error && <div className="error-text">{error}</div>}

          <h3 style={{ margin: "14px 0 8px" }}>Сообщения по записи</h3>
          {b.messages?.length ? (
            <div className="msg-history">
              {b.messages.map((m: any) => (
                <div className="msg-item" key={m.id}>
                  <div className="msg-meta">
                    {dayjs(m.sent_at).format("D MMM HH:mm")} · {m.kind_display} ·
                    <Badge value={m.channel} label={m.channel.toUpperCase()} />
                    <Badge value={m.delivery_status ?? "sent"} label={m.delivery_status ?? ""} />
                    {m.cost > 0 && <span>{m.cost} ₽</span>}
                  </div>
                  {m.text}
                </div>
              ))}
            </div>
          ) : <Empty text="Сообщений ещё не было" />}
        </>
      )}
    </Modal>
  );
}

export default function BookingsPage() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [showNew, setShowNew] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api("/api/settings/staff") });

  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";
  const status = params.get("status") ?? "";
  const staffId = params.get("staff_id") ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  const qs = new URLSearchParams({ page: String(page), page_size: "50" });
  if (dateFrom) qs.set("date_from", dateFrom);
  if (dateTo) qs.set("date_to", dateTo);
  if (status) qs.set("status", status);
  if (staffId) qs.set("staff_id", staffId);

  const bookings = useQuery({
    queryKey: ["bookings", qs.toString()],
    queryFn: () => api(`/api/bookings?${qs}`),
    // при листании держим прошлую страницу, чтобы таблица не мигала пустотой
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="page-head">
        <h1>Записи</h1>
        <button className="btn-primary" onClick={() => setShowNew(true)}>+ Добавить запись</button>
      </div>
      <div className="filters">
        <input type="date" value={dateFrom} onChange={(e) => setParam("date_from", e.target.value)} />
        <span>—</span>
        <input type="date" value={dateTo} onChange={(e) => setParam("date_to", e.target.value)} />
        <select value={status} onChange={(e) => setParam("status", e.target.value)}>
          <option value="">Все статусы</option>
          {STATUS_OPTIONS.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
        </select>
        <select value={staffId} onChange={(e) => setParam("staff_id", e.target.value)}>
          <option value="">Все мастера</option>
          {(staff.data?.items ?? []).map((s: any) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        {(dateFrom || dateTo || status || staffId) && (
          <button className="link-btn" onClick={() => setParams({}, { replace: true })}>Сбросить</button>
        )}
      </div>

      {bookings.isLoading ? <Spinner /> : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Дата</th><th>Время</th><th>Клиент</th><th>Услуга</th>
                    <th>Мастер</th><th>Статус</th><th>Источник</th></tr>
              </thead>
              <tbody>
                {(bookings.data?.items ?? []).map((b: any) => (
                  <tr key={b.id} className="clickable" onClick={() => setOpenId(b.id)}>
                    <td>{dayjs(b.starts_at).format("D MMM YYYY")}</td>
                    <td><b>{dayjs(b.starts_at).format("HH:mm")}</b></td>
                    <td>{b.customer?.name ?? "—"}</td>
                    <td>{b.service?.name}</td>
                    <td>{b.staff?.name ?? "любой"}</td>
                    <td><Badge value={b.status} label={b.status_display} /></td>
                    <td>{{ bot: "бот", manual: "вручную", yclients: "YCLIENTS" }[b.source as string] ?? b.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!bookings.data?.items?.length && <Empty text="Записей не найдено" />}
          </div>
          <Pager page={page} total={bookings.data?.total ?? 0} pageSize={50} onPage={setPage} />
        </>
      )}

      {showNew && <NewBookingModal onClose={() => setShowNew(false)} />}
      {openId !== null && <BookingModal id={openId} onClose={() => setOpenId(null)} />}
    </>
  );
}

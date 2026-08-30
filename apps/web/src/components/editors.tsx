/* Редакторы настроек: используются и в «Настройках», и в онбординг-мастере. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText } from "../api/client";
import { Empty, Field, Modal, Spinner, money } from "./ui";

/* ── Услуги ──────────────────────────────────────────────────────────── */
function ServiceForm({ initial, onDone }: { initial?: any; onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [price, setPrice] = useState(initial?.price ?? "");
  const [duration, setDuration] = useState(initial?.duration_min ?? 60);
  const [cycle, setCycle] = useState(initial?.repeat_cycle_days ?? "");
  const [error, setError] = useState("");

  const save = async () => {
    setError("");
    try {
      const body = {
        name, price: Number(price), duration_min: Number(duration),
        repeat_cycle_days: cycle === "" ? null : Number(cycle),
      };
      if (initial?.id) {
        await api(`/api/settings/services/${initial.id}`, { method: "PATCH", body });
      } else {
        await api("/api/settings/services", { method: "POST", body });
      }
      qc.invalidateQueries({ queryKey: ["services"] });
      onDone();
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <>
      <Field label="Название"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <div className="form-row">
        <Field label="Цена, ₽">
          <input type="number" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
        <Field label="Длительность, мин">
          <input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} /></Field>
        <Field label="Цикл повтора, дней">
          <input type="number" value={cycle} placeholder="пусто = без реактивации"
                 onChange={(e) => setCycle(e.target.value)} /></Field>
      </div>
      {error && <div className="error-text">{error}</div>}
      <button className="btn-primary" onClick={save} disabled={!name || !price}>Сохранить</button>
    </>
  );
}

export function ServicesEditor() {
  const services = useQuery({ queryKey: ["services"], queryFn: () => api("/api/settings/services") });
  const qc = useQueryClient();
  const [editing, setEditing] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);

  const deactivate = async (id: number) => {
    await api(`/api/settings/services/${id}`, { method: "DELETE" });
    qc.invalidateQueries({ queryKey: ["services"] });
  };

  if (services.isLoading) return <Spinner />;
  const items = services.data?.items ?? [];
  return (
    <>
      <div className="table-wrap" style={{ marginBottom: 12 }}>
        <table>
          <thead><tr><th>Услуга</th><th>Цена</th><th>Длительность</th><th>Цикл</th><th /></tr></thead>
          <tbody>
            {items.map((s: any) => (
              <tr key={s.id} style={s.is_active ? undefined : { opacity: 0.45 }}>
                <td><b>{s.name}</b></td>
                <td>{money(s.price)}</td>
                <td>{s.duration_min} мин</td>
                <td>{s.repeat_cycle_days ? `${s.repeat_cycle_days} дн.` : "—"}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-sm" onClick={() => setEditing(s)}>Изменить</button>{" "}
                  {s.is_active && (
                    <button className="btn-sm btn-danger" onClick={() => deactivate(s.id)}>
                      Скрыть
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <Empty text="Добавьте первую услугу" />}
      </div>
      <button onClick={() => setAdding(true)}>+ Добавить услугу</button>
      {(adding || editing) && (
        <Modal title={editing ? "Услуга" : "Новая услуга"}
               onClose={() => { setAdding(false); setEditing(null); }}>
          <ServiceForm initial={editing ?? undefined}
                       onDone={() => { setAdding(false); setEditing(null); }} />
        </Modal>
      )}
    </>
  );
}

/* ── Мастера ─────────────────────────────────────────────────────────── */
export function StaffEditor() {
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api("/api/settings/staff") });
  const qc = useQueryClient();
  const [name, setName] = useState("");

  const add = async () => {
    await api("/api/settings/staff", { method: "POST", body: { name } });
    setName("");
    qc.invalidateQueries({ queryKey: ["staff"] });
  };
  const deactivate = async (id: number) => {
    await api(`/api/settings/staff/${id}`, { method: "DELETE" });
    qc.invalidateQueries({ queryKey: ["staff"] });
  };

  if (staff.isLoading) return <Spinner />;
  const items = staff.data?.items ?? [];
  return (
    <>
      <div className="table-wrap" style={{ marginBottom: 12 }}>
        <table>
          <tbody>
            {items.map((s: any) => (
              <tr key={s.id} style={s.is_active ? undefined : { opacity: 0.45 }}>
                <td><b>{s.name}</b></td>
                <td style={{ textAlign: "right" }}>
                  {s.is_active && (
                    <button className="btn-sm btn-danger" onClick={() => deactivate(s.id)}>
                      Скрыть
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <Empty text="Добавьте мастеров" />}
      </div>
      <div className="form-row" style={{ maxWidth: 380 }}>
        <input placeholder="Имя мастера" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn-primary" style={{ flex: "0 0 auto" }} disabled={!name} onClick={add}>
          Добавить
        </button>
      </div>
    </>
  );
}

/* ── Часы работы ─────────────────────────────────────────────────────── */
const DAY_LABELS: [string, string][] = [
  ["mon", "Понедельник"], ["tue", "Вторник"], ["wed", "Среда"], ["thu", "Четверг"],
  ["fri", "Пятница"], ["sat", "Суббота"], ["sun", "Воскресенье"],
];

export function HoursEditor({
  value, onSave,
}: { value: Record<string, [string, string] | null>; onSave: (hours: any) => Promise<void> }) {
  // состояние формы принадлежит пользователю: инициализируем один раз,
  // а не синхронизируем эффектом (иначе лишний рендер и затирание правок)
  const [hours, setHours] = useState<Record<string, [string, string] | null>>(() => {
    const init: Record<string, [string, string] | null> = {};
    for (const [key] of DAY_LABELS) {
      const entry: any = (value as any)?.[key];
      init[key] = entry ? [entry[0], entry[1]] : null;
    }
    return init;
  });
  const [busy, setBusy] = useState(false);

  const set = (day: string, idx: 0 | 1, v: string) => {
    setHours((h) => {
      const cur = h[day] ?? ["10:00", "20:00"];
      const next: [string, string] = idx === 0 ? [v, cur[1]] : [cur[0], v];
      return { ...h, [day]: next };
    });
  };

  const save = async () => {
    setBusy(true);
    const out: Record<string, [string, string]> = {};
    for (const [key, entry] of Object.entries(hours)) if (entry) out[key] = entry;
    await onSave(out);
    setBusy(false);
  };

  return (
    <>
      {DAY_LABELS.map(([key, label]) => (
        <div key={key} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
          <label style={{ width: 130, display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={hours[key] != null}
                   onChange={(e) => setHours((h) => ({ ...h, [key]: e.target.checked ? ["10:00", "20:00"] : null }))} />
            {label}
          </label>
          {hours[key] ? (
            <>
              <input type="time" style={{ width: 110 }} value={hours[key]![0]}
                     onChange={(e) => set(key, 0, e.target.value)} />
              <span>—</span>
              <input type="time" style={{ width: 110 }} value={hours[key]![1]}
                     onChange={(e) => set(key, 1, e.target.value)} />
            </>
          ) : <span className="hint">выходной</span>}
        </div>
      ))}
      <button className="btn-primary" style={{ marginTop: 8 }} disabled={busy} onClick={save}>
        Сохранить часы
      </button>
    </>
  );
}

/* ── Тексты сообщений ────────────────────────────────────────────────── */
const TEXT_LABELS: [string, string][] = [
  ["reminder_24h", "Напоминание за 24 часа"],
  ["reminder_3h", "Напоминание за 3 часа"],
  ["sms_chase", "SMS-догон (если не подтвердил)"],
  ["confirm", "Подтверждение записи"],
  ["reactivation", "Реактивация «спящего» клиента"],
];

export function TextsEditor({
  value, onSave,
}: { value: Record<string, string>; onSave: (texts: Record<string, string>) => Promise<void> }) {
  const [texts, setTexts] = useState<Record<string, string>>(() => ({ ...value }));
  const [busy, setBusy] = useState(false);

  return (
    <>
      <p className="hint" style={{ marginBottom: 12 }}>
        Подстановки: {"{имя} {дата} {время} {услуга} {мастер} {салон}"}
      </p>
      {TEXT_LABELS.map(([key, label]) => (
        <Field key={key} label={label}>
          <textarea value={texts[key] ?? ""}
                    onChange={(e) => setTexts((t) => ({ ...t, [key]: e.target.value }))} />
        </Field>
      ))}
      <button className="btn-primary" disabled={busy}
              onClick={async () => { setBusy(true); await onSave(texts); setBusy(false); }}>
        Сохранить тексты
      </button>
    </>
  );
}

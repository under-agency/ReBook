/* Редакторы настроек: используются и в «Настройках», и в онбординг-мастере. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus } from "lucide-react";
import { api, errorText } from "../api/client";
import { useToast } from "./toast";
import { Button, Empty, Field, Modal, Skeleton, TableSkeleton, money } from "./ui";

/* ── Услуги ──────────────────────────────────────────────────────────── */
function ServiceForm({ initial, onDone }: { initial?: any; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(initial?.name ?? "");
  const [price, setPrice] = useState(initial?.price ?? "");
  const [duration, setDuration] = useState(initial?.duration_min ?? 60);
  const [cycle, setCycle] = useState(initial?.repeat_cycle_days ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setError("");
    setBusy(true);
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
      toast.ok(initial?.id ? "Услуга обновлена" : "Услуга добавлена");
      onDone();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Field label="Название">
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="form-row">
        <Field label="Цена, ₽">
          <input type="number" value={price} onChange={(e) => setPrice(e.target.value)} />
        </Field>
        <Field label="Длительность, мин">
          <input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} />
        </Field>
        <Field label="Цикл повтора, дней">
          <input type="number" value={cycle} placeholder="пусто = без реактивации"
                 onChange={(e) => setCycle(e.target.value)} />
        </Field>
      </div>
      <p className="hint mb-3">
        Цикл повтора — через сколько дней услугу обычно повторяют. По нему бот находит
        «спящих» клиентов.
      </p>
      {error && <div className="error-text">{error}</div>}
      <Button variant="primary" onClick={save} disabled={busy || !name || !price}>
        {busy ? "Сохраняем…" : "Сохранить"}
      </Button>
    </>
  );
}

export function ServicesEditor() {
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api<any>("/api/settings/services"),
  });
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);

  const deactivate = async (s: any) => {
    if (!window.confirm(`Скрыть услугу «${s.name}»? Прошлые записи останутся на месте.`)) return;
    try {
      await api(`/api/settings/services/${s.id}`, { method: "DELETE" });
      qc.invalidateQueries({ queryKey: ["services"] });
      toast.ok(`Услуга «${s.name}» скрыта`);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  if (services.isLoading) return <TableSkeleton rows={4} cols={4} />;
  const items = services.data?.items ?? [];

  return (
    <>
      <div className="table-wrap mb-3">
        <table>
          <thead>
            <tr><th>Услуга</th><th className="t-num">Цена</th>
                <th className="t-num">Длительность</th><th>Цикл повтора</th><th /></tr>
          </thead>
          <tbody>
            {items.map((s: any) => (
              <tr key={s.id} className={s.is_active ? undefined : "dim"}>
                <td className="strong">{s.name}</td>
                <td className="t-num">{money(s.price)}</td>
                <td className="t-num">{s.duration_min} мин</td>
                <td className="muted">
                  {s.repeat_cycle_days ? `${s.repeat_cycle_days} дн.` : "—"}
                </td>
                <td>
                  <div className="row push nowrap" style={{ justifyContent: "flex-end" }}>
                    <Button size="sm" onClick={() => setEditing(s)}>Изменить</Button>
                    {s.is_active && (
                      <Button size="sm" variant="danger" onClick={() => deactivate(s)}>Скрыть</Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && (
          <Empty text="Услуг пока нет"
                 hint="Без услуг бот не сможет записывать — добавьте хотя бы одну." />
        )}
      </div>
      <Button onClick={() => setAdding(true)}><Plus size={14} /> Добавить услугу</Button>
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
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any>("/api/settings/staff") });
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    try {
      await api("/api/settings/staff", { method: "POST", body: { name } });
      setName("");
      qc.invalidateQueries({ queryKey: ["staff"] });
      toast.ok("Мастер добавлен");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async (s: any) => {
    if (!window.confirm(`Скрыть мастера «${s.name}»? Прошлые записи останутся на месте.`)) return;
    try {
      await api(`/api/settings/staff/${s.id}`, { method: "DELETE" });
      qc.invalidateQueries({ queryKey: ["staff"] });
      toast.ok(`Мастер «${s.name}» скрыт`);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  if (staff.isLoading) return <TableSkeleton rows={3} cols={2} />;
  const items = staff.data?.items ?? [];

  return (
    <>
      <div className="table-wrap mb-3">
        <table>
          <tbody>
            {items.map((s: any) => (
              <tr key={s.id} className={s.is_active ? undefined : "dim"}>
                <td className="strong">{s.name}</td>
                <td>
                  <div className="row nowrap" style={{ justifyContent: "flex-end" }}>
                    {s.is_active && (
                      <Button size="sm" variant="danger" onClick={() => deactivate(s)}>Скрыть</Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && (
          <Empty text="Мастеров пока нет"
                 hint="Если мастеров нет, бот будет записывать «к любому»." />
        )}
      </div>
      <form className="row narrow"
            onSubmit={(e) => { e.preventDefault(); if (name) add(); }}>
        <input placeholder="Имя мастера" value={name} aria-label="Имя мастера"
               onChange={(e) => setName(e.target.value)} />
        <Button type="submit" variant="primary" disabled={busy || !name}>Добавить</Button>
      </form>
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
      <div className="stack mb-4" style={{ gap: "var(--sp-2)" }}>
        {DAY_LABELS.map(([key, label]) => (
          <div className="row" key={key}>
            <label className="row" style={{ width: 150 }}>
              <input type="checkbox" checked={hours[key] != null}
                     onChange={(e) => setHours((h) => ({
                       ...h, [key]: e.target.checked ? ["10:00", "20:00"] : null,
                     }))} />
              {label}
            </label>
            {hours[key] ? (
              <>
                <input type="time" style={{ width: 110 }} value={hours[key]![0]}
                       aria-label={`${label}: начало`}
                       onChange={(e) => set(key, 0, e.target.value)} />
                <span className="dim">—</span>
                <input type="time" style={{ width: 110 }} value={hours[key]![1]}
                       aria-label={`${label}: конец`}
                       onChange={(e) => set(key, 1, e.target.value)} />
              </>
            ) : <span className="hint">выходной</span>}
          </div>
        ))}
      </div>
      <Button variant="primary" disabled={busy} onClick={save}>
        {busy ? "Сохраняем…" : "Сохранить часы"}
      </Button>
    </>
  );
}

/* ── Тексты сообщений ────────────────────────────────────────────────── */
const TEXT_LABELS: [string, string][] = [
  ["reminder_24h", "Напоминание за 24 часа"],
  ["reminder_3h", "Напоминание за 3 часа"],
  ["sms_chase", "SMS-догон, если не подтвердил"],
  ["confirm", "Подтверждение записи"],
  ["reactivation", "Реактивация «спящего» клиента"],
  ["faq", "О салоне для ИИ-ассистента: адрес, как добраться, оплата, правила (без подстановок)"],
];

export function TextsEditor({
  value, onSave,
}: { value: Record<string, string>; onSave: (texts: Record<string, string>) => Promise<void> }) {
  const [texts, setTexts] = useState<Record<string, string>>(() => ({ ...value }));
  const [busy, setBusy] = useState(false);

  return (
    <>
      <p className="hint mb-3">
        Подстановки: <span className="mono">{"{имя} {дата} {время} {услуга} {мастер} {салон}"}</span>
      </p>
      {TEXT_LABELS.map(([key, label]) => (
        <Field key={key} label={label}>
          <textarea value={texts[key] ?? ""}
                    onChange={(e) => setTexts((t) => ({ ...t, [key]: e.target.value }))} />
        </Field>
      ))}
      <Button variant="primary" disabled={busy}
              onClick={async () => { setBusy(true); await onSave(texts); setBusy(false); }}>
        {busy ? "Сохраняем…" : "Сохранить тексты"}
      </Button>
    </>
  );
}

/** Заглушка для мест, где ещё нужен простой каркас загрузки. */
export function EditorSkeleton() {
  return (
    <div className="stack">
      <Skeleton w="40%" h={14} /><Skeleton w="100%" h={30} /><Skeleton w="100%" h={30} />
    </div>
  );
}

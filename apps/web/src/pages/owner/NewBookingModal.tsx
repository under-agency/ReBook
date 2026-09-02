import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { api, errorText } from "../../api/client";
import { useToast } from "../../components/toast";
import { Button, Field, Modal, money } from "../../components/ui";
import SlotPicker from "./SlotPicker";

export type NewBookingPreset = {
  /** День и мастер из ячейки календаря; точное время выбирается из свободных окон */
  date?: string;
  staffId?: number;
};

export default function NewBookingModal({
  onClose, preset,
}: { onClose: () => void; preset?: NewBookingPreset }) {
  const qc = useQueryClient();
  const toast = useToast();
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api<any>("/api/settings/services"),
  });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any>("/api/settings/staff") });

  const [customerQuery, setCustomerQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [customerId, setCustomerId] = useState<number | "">("");
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [serviceId, setServiceId] = useState<number | "">("");
  const [staffId, setStaffId] = useState<number | "">(preset?.staffId ?? "");
  const [date, setDate] = useState(preset?.date ?? dayjs().format("YYYY-MM-DD"));
  const [slot, setSlot] = useState("");
  const [note, setNote] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Поиск клиента бил запросом на каждое нажатие — придерживаем
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(customerQuery), 300);
    return () => window.clearTimeout(t);
  }, [customerQuery]);

  const found = useQuery({
    queryKey: ["customer-search", debounced],
    enabled: debounced.length >= 2,
    queryFn: () => api<any>(`/api/customers?q=${encodeURIComponent(debounced)}&page_size=8`),
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
      qc.invalidateQueries({ queryKey: ["calendar"] });
      toast.ok(`Записали на ${dayjs(slot).format("D MMMM, HH:mm")}`);
      onClose();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.warnings) setWarnings(e.detail.warnings);
      else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Новая запись" onClose={onClose}>
      <Field label="Клиент — поиск по имени или телефону">
        <input value={customerQuery} placeholder="Начните вводить…"
               onChange={(e) => { setCustomerQuery(e.target.value); setCustomerId(""); }} />
      </Field>
      {debounced.length >= 2 && !customerId && (
        <div className="chips mb-3">
          {(found.data?.items ?? []).map((c: any) => (
            <button type="button" key={c.id} className="chip"
                    onClick={() => {
                      setCustomerId(c.id);
                      setCustomerQuery(`${c.name ?? ""} ${c.phone ?? ""}`.trim());
                    }}>
              {c.name} {c.phone}
            </button>
          ))}
          {found.data && !found.data.items.length && (
            <span className="hint">Не найдено — создадим нового</span>
          )}
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
          <select value={serviceId}
                  onChange={(e) => { setServiceId(Number(e.target.value) || ""); setSlot(""); }}>
            <option value="">—</option>
            {(services.data?.items ?? []).filter((s: any) => s.is_active).map((s: any) => (
              <option key={s.id} value={s.id}>{s.name} · {money(s.price)}</option>
            ))}
          </select>
        </Field>
        <Field label="Мастер">
          <select value={staffId}
                  onChange={(e) => { setStaffId(Number(e.target.value) || ""); setSlot(""); }}>
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
        <div className="card mb-3">
          <div className="row mb-2" style={{ color: "var(--warn)" }}>
            <TriangleAlert size={15} />
            <span className="strong">Время спорное</span>
          </div>
          <div className="muted mb-3">{warnings.join("; ")}</div>
          <Button variant="danger" disabled={busy} onClick={() => submit(true)}>
            Всё равно записать
          </Button>
        </div>
      )}
      {error && <div className="error-text">{error}</div>}

      <Button variant="primary" disabled={busy} onClick={() => submit(false)}>
        {busy ? "Сохраняем…" : "Записать"}
      </Button>
    </Modal>
  );
}

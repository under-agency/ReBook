import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, errorText } from "../../api/client";
import { CascadeChain, cascadeFromStatus } from "../../components/icons";
import { useToast } from "../../components/toast";
import {
  Button, Empty, Field, LoadError, Modal, Skeleton, Status, Tag, money,
} from "../../components/ui";
import SlotPicker from "./SlotPicker";

const MANUAL_STATUSES: [string, string][] = [
  ["confirmed", "Придёт"], ["done", "Состоялась"],
  ["cancelled", "Отменена"], ["no_show", "Неявка"], ["new", "Новая"],
];

const SOURCE_LABELS: Record<string, string> = {
  bot: "бот", manual: "вручную", yclients: "YCLIENTS",
};

const DELIVERY_LABELS: Record<string, string> = {
  sent: "доставлено", stub: "заглушка", failed: "ошибка",
};

export default function BookingModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState("");
  const [resched, setResched] = useState(false);
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [slot, setSlot] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  const booking = useQuery({
    queryKey: ["booking", id],
    queryFn: () => api<any>(`/api/bookings/${id}`),
  });
  const b = booking.data;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["booking", id] });
    qc.invalidateQueries({ queryKey: ["bookings"] });
    qc.invalidateQueries({ queryKey: ["upcoming"] });
    qc.invalidateQueries({ queryKey: ["calendar"] });
  };

  const setStatus = async (status: string, label: string) => {
    setError("");
    try {
      await api(`/api/bookings/${id}`, { method: "PATCH", body: { status } });
      refresh();
      toast.ok(`Статус изменён: ${label.toLowerCase()}`);
    } catch (e) {
      const text = errorText(e);
      setError(text);
      toast.error(text);
    }
  };

  const doResched = async (force = false) => {
    setError("");
    setWarnings([]);
    try {
      await api(`/api/bookings/${id}/reschedule`, {
        method: "POST", body: { starts_at: slot, staff_id: b?.staff?.id ?? null, force },
      });
      refresh();
      toast.ok(`Перенесли на ${dayjs(slot).format("D MMMM, HH:mm")}`);
      onClose();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.warnings) setWarnings(e.detail.warnings);
      else {
        const text = errorText(e);
        setError(text);
        toast.error(text);
      }
    }
  };

  const cascade = b ? cascadeFromStatus(b.status) : null;

  return (
    <Modal title={`Запись № ${id}`} onClose={onClose} wide>
      {booking.isError ? (
        <LoadError onRetry={() => booking.refetch()} />
      ) : booking.isLoading || !b ? (
        <div className="stack">
          <Skeleton w="60%" h={14} />
          <Skeleton w="80%" h={14} />
          <Skeleton w="45%" h={14} />
        </div>
      ) : (
        <>
          <dl className="kv">
            <dt>Клиент</dt>
            <dd>
              {b.customer?.name}
              <span className="mono muted"> · {b.customer?.phone ?? "без телефона"}</span>
              {b.customer?.has_tg && <> <Tag>Telegram</Tag></>}
            </dd>
            <dt>Услуга</dt>
            <dd>{b.service?.name} <span className="mono muted">{money(b.service?.price ?? 0)}</span></dd>
            <dt>Мастер</dt><dd>{b.staff?.name ?? "любой"}</dd>
            <dt>Когда</dt>
            <dd className="mono">
              {dayjs(b.starts_at).format("D MMMM YYYY, HH:mm")} · {b.duration_min} мин
            </dd>
            <dt>Статус</dt><dd><Status value={b.status} label={b.status_display} /></dd>
            {cascade && (<><dt>Каскад напоминаний</dt><dd><CascadeChain state={cascade} /></dd></>)}
            <dt>Источник</dt><dd>{SOURCE_LABELS[b.source as string] ?? b.source}</dd>
            {b.note && (<><dt>Комментарий</dt><dd>{b.note}</dd></>)}
          </dl>

          <div className="chips mb-3">
            {MANUAL_STATUSES.filter(([s]) => s !== b.status).map(([s, label]) => (
              <button key={s} className="chip" onClick={() => setStatus(s, label)}>{label}</button>
            ))}
            <button className="chip" onClick={() => setResched(!resched)}>
              <RefreshCw size={12} /> Перенести
            </button>
          </div>

          {resched && (
            <div className="card">
              <Field label="Новый день">
                <input type="date" value={date}
                       onChange={(e) => { setDate(e.target.value); setSlot(""); }} />
              </Field>
              <SlotPicker serviceId={b.service.id} staffId={b.staff?.id ?? ""}
                          date={date} value={slot} onChange={setSlot} />
              {warnings.length > 0 && (
                <div className="mt-3">
                  <div className="muted mb-2">{warnings.join("; ")}</div>
                  <Button variant="danger" onClick={() => doResched(true)}>
                    Всё равно перенести
                  </Button>
                </div>
              )}
              <div className="mt-3">
                <Button variant="primary" disabled={!slot} onClick={() => doResched(false)}>
                  Перенести
                </Button>
              </div>
            </div>
          )}
          {error && <div className="error-text">{error}</div>}

          <h3 className="mt-4 mb-2">Сообщения по записи</h3>
          {b.messages?.length ? (
            <div className="msg-history">
              {b.messages.map((m: any) => (
                <div className="msg-item" key={m.id}>
                  <div className="msg-meta">
                    <span className="mono">{dayjs(m.sent_at).format("D MMM HH:mm")}</span>
                    <span>{m.kind_display}</span>
                    <Tag>{m.channel.toUpperCase()}</Tag>
                    <Status value={m.delivery_status ?? "sent"}
                            label={DELIVERY_LABELS[m.delivery_status as string] ?? "доставлено"} />
                    {m.cost > 0 && <span className="mono">{m.cost} ₽</span>}
                  </div>
                  {m.text}
                </div>
              ))}
            </div>
          ) : (
            <Empty text="Сообщений ещё не было"
                   hint="Напоминание уйдёт за 24 часа до визита." />
          )}
        </>
      )}
    </Modal>
  );
}

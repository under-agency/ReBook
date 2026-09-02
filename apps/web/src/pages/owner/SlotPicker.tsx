import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Skeleton } from "../../components/ui";

export default function SlotPicker({
  serviceId, staffId, date, value, onChange,
}: {
  serviceId: number | "";
  staffId: number | "";
  date: string;
  value: string;
  onChange: (iso: string) => void;
}) {
  const slots = useQuery({
    queryKey: ["slots", serviceId, staffId, date],
    enabled: Boolean(serviceId && date),
    queryFn: () => api<{ slots: { starts_at: string; label: string }[] }>(
      `/api/bookings/free-slots?service_id=${serviceId}&date=${date}` +
      (staffId ? `&staff_id=${staffId}` : ""),
    ),
  });

  if (!serviceId || !date) return <div className="hint">Выберите услугу и день</div>;
  if (slots.isLoading) {
    return (
      <div className="slot-grid">
        {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} w={56} h={28} />)}
      </div>
    );
  }
  if (slots.isError) return <div className="error-text">Не удалось загрузить свободные окна</div>;

  const items = slots.data?.slots ?? [];
  if (!items.length) {
    return <div className="hint">Свободных окон нет — выберите другой день или мастера</div>;
  }

  return (
    <div className="slot-grid">
      {items.map((s) => (
        <button type="button" key={s.starts_at}
                className={"slot" + (value === s.starts_at ? " slot-active" : "")}
                onClick={() => onChange(s.starts_at)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}

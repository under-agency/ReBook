import dayjs from "dayjs";
import { Wrench } from "lucide-react";
import { Empty } from "./ui";

export type AuditRow = {
  id: number;
  action: string;
  entity: string | null;
  entity_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  is_support: boolean;
  user_email: string | null;
  salon_id?: number | null;
  ip: string | null;
  created_at: string;
};

const ACTIONS: Record<string, string> = {
  create: "создание",
  update: "изменение",
  deactivate: "отключение",
  status_change: "смена статуса",
  reschedule: "перенос",
  login: "вход",
  accept_invite: "принято приглашение",
  reissue_invite: "новое приглашение",
  test_reminder: "тестовое напоминание",
  support_enter: "вход в режим поддержки",
  support_exit: "выход из режима поддержки",
};

const ENTITIES: Record<string, string> = {
  booking: "запись",
  customer: "клиент",
  service: "услуга",
  staff: "мастер",
  salon: "салон",
  salon_settings: "настройки",
  payment: "платёж",
  user: "пользователь",
};

const FIELDS: Record<string, string> = {
  status: "статус",
  name: "название",
  phone: "телефон",
  price: "цена",
  starts_at: "время",
  duration_min: "длительность",
  do_not_disturb: "исключён из рассылок",
  avg_check: "средний чек",
  is_active: "активен",
};

/** Коды статусов в журнале читаются так же, как в интерфейсе. */
const VALUES: Record<string, string> = {
  new: "Новая", reminded_24h: "Ждём ответ", reminded_sms: "Ждём ответ (SMS)",
  confirmed: "Придёт", done: "Состоялась", rescheduled: "Перенесена",
  cancelled: "Отменена", no_show: "Неявка",
  onboarding: "Внедрение", active: "Активен", grace: "Просрочка",
  paused: "Приостановлен", archived: "Архив",
};

const show = (v: unknown) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "да" : "нет";
  if (typeof v === "object") return JSON.stringify(v);
  const raw = String(v);
  return VALUES[raw] ?? raw;
};

/** Показываем только поля, которые действительно изменились. */
function Diff({ before, after }: { before: AuditRow["before"]; after: AuditRow["after"] }) {
  if (!before && !after) return <span className="dim">—</span>;
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]))
    .filter((k) => show(before?.[k]) !== show(after?.[k]));
  if (!keys.length) return <span className="dim">—</span>;

  return (
    <span className="diff">
      {keys.slice(0, 4).map((k) => (
        <span key={k}>
          <span className="dim">{FIELDS[k] ?? k}: </span>
          {before && k in before && <span className="diff-from">{show(before[k])}</span>}
          {before && k in before && <span className="diff-arrow"> → </span>}
          <span className="diff-to">{show(after?.[k])}</span>
        </span>
      ))}
      {keys.length > 4 && <span className="dim">и ещё {keys.length - 4}</span>}
    </span>
  );
}

export default function AuditTable({
  rows, withSalon, emptyText = "Изменений пока нет",
}: { rows: AuditRow[]; withSalon?: boolean; emptyText?: string }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Когда</th>
            {withSalon && <th>Салон</th>}
            <th>Кто</th>
            <th>Действие</th>
            <th>Объект</th>
            <th>Что изменилось</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id} className={a.is_support ? "audit-support" : undefined}>
              <td className="t-time nowrap">{dayjs(a.created_at).format("D MMM HH:mm")}</td>
              {withSalon && <td className="mono">{a.salon_id ? `#${a.salon_id}` : "—"}</td>}
              <td className="t-trunc">
                {a.user_email ?? <span className="dim">система</span>}
                {a.is_support && (
                  <span className="row nowrap" style={{ color: "var(--warn)" }}>
                    <Wrench size={12} /> поддержка
                  </span>
                )}
              </td>
              <td>{ACTIONS[a.action] ?? a.action}</td>
              <td className="muted">
                {a.entity ? (ENTITIES[a.entity] ?? a.entity) : "—"}
                {a.entity_id ? <span className="mono"> №{a.entity_id}</span> : ""}
              </td>
              <td><Diff before={a.before} after={a.after} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <Empty text={emptyText}
               hint="Сюда попадают правки записей и настроек, а также действия поддержки." />
      )}
    </div>
  );
}

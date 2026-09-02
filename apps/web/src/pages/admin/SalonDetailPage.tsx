import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Copy, Link2, Wrench } from "lucide-react";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import AuditTable, { type AuditRow } from "../../components/AuditTable";
import { PageActions } from "../../components/Layout";
import { useToast } from "../../components/toast";
import {
  Button, Empty, Field, LoadError, Status, TableSkeleton, Tabs, money,
} from "../../components/ui";
import { SALON_STATUS_LABELS } from "./SalonsListPage";

const FLAG_LABELS: Record<string, string> = {
  reactivation: "Реактивация базы", max_channel: "Канал MAX",
  waitlist: "Лист ожидания", llm_faq: "FAQ с LLM", yclients: "Синхронизация YCLIENTS",
};

function Overview({ salon, onSaved }: { salon: any; onSaved: () => void }) {
  const toast = useToast();
  // форма пересоздаётся через key={salon.id} при переходе к другому салону
  const [form, setForm] = useState<any>(() => ({
    name: salon.name, status: salon.status,
    avg_check: salon.avg_check ?? "", sms_limit_month: salon.sms_limit_month,
    monthly_fee: salon.monthly_fee ?? "",
    next_payment_at: salon.next_payment_at ?? "",
    tg_bot_token: "",
  }));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const body: any = {
        name: form.name, status: form.status,
        avg_check: form.avg_check ? Number(form.avg_check) : null,
        sms_limit_month: Number(form.sms_limit_month),
        monthly_fee: form.monthly_fee ? Number(form.monthly_fee) : null,
        next_payment_at: form.next_payment_at || null,
      };
      if (form.tg_bot_token) body.tg_bot_token = form.tg_bot_token;
      await api(`/api/admin/salons/${salon.id}`, { method: "PATCH", body });
      onSaved();
      toast.ok("Салон сохранён");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="narrow">
      <Field label="Название"><input value={form.name ?? ""} onChange={set("name")} /></Field>
      <div className="form-row">
        <Field label="Статус">
          <select value={form.status ?? ""} onChange={set("status")}>
            {Object.entries(SALON_STATUS_LABELS).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </Field>
        <Field label="Средний чек, ₽">
          <input type="number" value={form.avg_check ?? ""} onChange={set("avg_check")} />
        </Field>
      </div>
      <div className="form-row">
        <Field label="Лимит SMS в месяц">
          <input type="number" value={form.sms_limit_month ?? ""} onChange={set("sms_limit_month")} />
        </Field>
        <Field label="Абонентка, ₽/мес">
          <input type="number" value={form.monthly_fee ?? ""} onChange={set("monthly_fee")} />
        </Field>
        <Field label="Следующий платёж">
          <input type="date" value={form.next_payment_at ?? ""} onChange={set("next_payment_at")} />
        </Field>
      </div>
      <Field label={"Токен Telegram-бота — " +
                    (salon.has_tg_bot ? "задан, ввод заменит" : "не задан")}>
        <input value={form.tg_bot_token ?? ""} onChange={set("tg_bot_token")}
               placeholder="оставьте пустым, чтобы не менять" />
      </Field>
      <Button variant="primary" disabled={busy} onClick={save}>
        {busy ? "Сохраняем…" : "Сохранить"}
      </Button>

      <h3 className="mt-4 mb-2">Пользователи</h3>
      {(salon.users ?? []).map((u: any) => (
        <div key={u.id} className="row">
          <span className="mono">{u.email}</span>
          <span className="dim">{u.role}</span>
          {u.invited && <span style={{ color: "var(--warn)" }}>приглашение не принято</span>}
        </div>
      ))}
    </div>
  );
}

function Billing({ salon, onSaved }: { salon: any; onSaved: () => void }) {
  const toast = useToast();
  const [amount, setAmount] = useState(salon.monthly_fee ?? "");
  const [start, setStart] = useState(dayjs().startOf("month").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(dayjs().endOf("month").format("YYYY-MM-DD"));
  const [paidAt, setPaidAt] = useState(dayjs().format("YYYY-MM-DD"));
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    try {
      await api(`/api/admin/salons/${salon.id}/payments`, {
        method: "POST",
        body: {
          amount: Number(amount), period_start: start, period_end: end,
          paid_at: paidAt || null,
        },
      });
      onSaved();
      toast.ok(`Оплата ${money(Number(amount))} зафиксирована`);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card">
        <h3 className="mb-3">Зафиксировать оплату</h3>
        <div className="form-row">
          <Field label="Сумма, ₽">
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Период с">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="по">
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Field label="Оплачено">
            <input type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} />
          </Field>
        </div>
        <Button variant="primary" onClick={add} disabled={busy || !amount}>Добавить</Button>
        <p className="hint mt-2">
          Оплата сдвигает дату следующего платежа и снимает статусы «просрочка» и
          «приостановлен».
        </p>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Период</th><th className="t-num">Сумма</th><th>Оплачено</th><th>Заметка</th></tr>
          </thead>
          <tbody>
            {(salon.payments ?? []).map((p: any) => (
              <tr key={p.id}>
                <td className="t-time nowrap">
                  {dayjs(p.period_start).format("D MMM")} — {dayjs(p.period_end).format("D MMM YYYY")}
                </td>
                <td className="t-num">{money(p.amount)}</td>
                <td>
                  {p.paid_at
                    ? <span className="t-time">{dayjs(p.paid_at).format("D MMM YYYY")}</span>
                    : <Status value="failed" label="не оплачено" />}
                </td>
                <td className="hint">{p.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!salon.payments?.length && <Empty text="Платежей ещё нет" />}
      </div>
    </>
  );
}

function Flags({ salon, onSaved }: { salon: any; onSaved: () => void }) {
  const toast = useToast();
  const [flags, setFlags] = useState<Record<string, boolean>>(
    () => ({ ...(salon.feature_flags ?? {}) }));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await api(`/api/admin/salons/${salon.id}`, {
        method: "PATCH", body: { feature_flags: flags },
      });
      onSaved();
      toast.ok("Флаги сохранены");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="narrow">
      <div className="stack mb-4" style={{ gap: "var(--sp-2)" }}>
        {Object.entries(FLAG_LABELS).map(([key, label]) => (
          <label key={key} className="row">
            <input type="checkbox" checked={Boolean(flags[key])}
                   onChange={(e) => setFlags({ ...flags, [key]: e.target.checked })} />
            {label}
          </label>
        ))}
      </div>
      <Button variant="primary" disabled={busy} onClick={save}>Сохранить флаги</Button>
      <p className="hint mt-2">
        Флаги нужны, чтобы продавать пакеты и выкатывать новое на одном салоне.
      </p>
    </div>
  );
}

function SalonAudit({ salonId }: { salonId: number }) {
  const audit = useQuery({
    queryKey: ["salon-audit", salonId],
    queryFn: () => api<{ items: AuditRow[] }>(
      `/api/admin/audit?salon_id=${salonId}&page_size=100`,
    ),
  });
  if (audit.isError) return <LoadError onRetry={() => audit.refetch()} />;
  if (audit.isLoading) return <TableSkeleton rows={6} cols={5} />;
  return <AuditTable rows={audit.data?.items ?? []} />;
}

export default function SalonDetailPage() {
  const { id } = useParams();
  const salonId = Number(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { refresh } = useAuth();
  const [tab, setTab] = useState("overview");
  const [inviteLink, setInviteLink] = useState("");

  const salon = useQuery({
    queryKey: ["salon", salonId],
    queryFn: () => api<any>(`/api/admin/salons/${salonId}`),
  });

  const onSaved = () => {
    qc.invalidateQueries({ queryKey: ["salon", salonId] });
    qc.invalidateQueries({ queryKey: ["salons"] });
  };

  const impersonate = async () => {
    try {
      await api(`/api/admin/salons/${salonId}/impersonate`, { method: "POST" });
      await refresh();
      navigate("/");
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const reinvite = async () => {
    try {
      const r = await api<any>(`/api/admin/salons/${salonId}/invite`, { method: "POST" });
      setInviteLink(`${window.location.origin}${r.invite_link}`);
      toast.ok("Ссылка выпущена — действует 72 часа");
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
      toast.ok("Ссылка скопирована");
    } catch {
      toast.error("Браузер не дал доступ к буферу — скопируйте вручную");
    }
  };

  if (salon.isError) return <LoadError onRetry={() => salon.refetch()} />;
  if (salon.isLoading || !salon.data) return <TableSkeleton rows={6} cols={3} />;
  const s = salon.data;

  return (
    <>
      <PageActions>
        <Button size="sm" onClick={reinvite}>
          <Link2 size={14} /> Новое приглашение
        </Button>
        <Button size="sm" variant="primary" onClick={impersonate}>
          <Wrench size={14} /> Режим поддержки
        </Button>
      </PageActions>

      <div className="section-head">
        <h1>{s.name}</h1>
        <Status value={s.status} label={SALON_STATUS_LABELS[s.status] ?? s.status} />
      </div>

      {inviteLink && (
        <div className="card">
          <div className="hint mb-2">Ссылка-приглашение владельцу, действует 72 часа</div>
          <div className="row">
            <span className="mono" style={{ wordBreak: "break-all" }}>{inviteLink}</span>
            <Button size="sm" onClick={copyLink}><Copy size={13} /> Скопировать</Button>
          </div>
        </div>
      )}

      <Tabs active={tab} onChange={setTab} tabs={[
        ["overview", "Обзор"], ["billing", "Биллинг"], ["flags", "Флаги"],
        ["audit", "Журнал"],
      ]} />
      {tab === "overview" && <Overview key={s.id} salon={s} onSaved={onSaved} />}
      {tab === "billing" && <Billing key={s.id} salon={s} onSaved={onSaved} />}
      {tab === "flags" && <Flags key={s.id} salon={s} onSaved={onSaved} />}
      {tab === "audit" && <SalonAudit salonId={salonId} />}
    </>
  );
}

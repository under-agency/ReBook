import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Empty, Field, Spinner, Tabs, money } from "../../components/ui";
import { SALON_STATUS_LABELS } from "./SalonsListPage";

const FLAG_LABELS: Record<string, string> = {
  reactivation: "Реактивация базы", max_channel: "Канал MAX",
  waitlist: "Лист ожидания", llm_faq: "FAQ с LLM", yclients: "Синхронизация YCLIENTS",
};

function Overview({ salon, onSaved }: { salon: any; onSaved: () => void }) {
  const [form, setForm] = useState<any>({});
  const [msg, setMsg] = useState("");
  useEffect(() => {
    setForm({
      name: salon.name, status: salon.status,
      avg_check: salon.avg_check ?? "", sms_limit_month: salon.sms_limit_month,
      monthly_fee: salon.monthly_fee ?? "",
      next_payment_at: salon.next_payment_at ?? "",
      tg_bot_token: "",
    });
  }, [salon]);

  const save = async () => {
    setMsg("");
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
      setMsg("Сохранено ✓");
    } catch (e) {
      setMsg(errorText(e));
    }
  };

  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  return (
    <div style={{ maxWidth: 520 }}>
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
        <Field label="Лимит SMS/мес">
          <input type="number" value={form.sms_limit_month ?? ""} onChange={set("sms_limit_month")} />
        </Field>
        <Field label="Абонентка, ₽/мес">
          <input type="number" value={form.monthly_fee ?? ""} onChange={set("monthly_fee")} />
        </Field>
        <Field label="Следующий платёж">
          <input type="date" value={form.next_payment_at ?? ""} onChange={set("next_payment_at")} />
        </Field>
      </div>
      <Field label={"Токен TG-бота " + (salon.has_tg_bot ? "(задан — ввод заменит)" : "(не задан)")}>
        <input value={form.tg_bot_token ?? ""} onChange={set("tg_bot_token")}
               placeholder="оставьте пустым, чтобы не менять" />
      </Field>
      {msg && <div className={msg.includes("✓") ? "hint" : "error-text"}>{msg}</div>}
      <button className="btn-primary" onClick={save}>Сохранить</button>

      <h3 style={{ margin: "18px 0 8px" }}>Пользователи</h3>
      {(salon.users ?? []).map((u: any) => (
        <div key={u.id} className="hint">
          {u.email} — {u.role}{u.invited ? " · приглашение не принято" : ""}
        </div>
      ))}
    </div>
  );
}

function Billing({ salon, onSaved }: { salon: any; onSaved: () => void }) {
  const [amount, setAmount] = useState(salon.monthly_fee ?? "");
  const [start, setStart] = useState(dayjs().startOf("month").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(dayjs().endOf("month").format("YYYY-MM-DD"));
  const [paidAt, setPaidAt] = useState(dayjs().format("YYYY-MM-DD"));
  const [error, setError] = useState("");

  const add = async () => {
    setError("");
    try {
      await api(`/api/admin/salons/${salon.id}/payments`, {
        method: "POST",
        body: { amount: Number(amount), period_start: start, period_end: end,
                paid_at: paidAt || null },
      });
      onSaved();
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <>
      <div className="card" style={{ maxWidth: 640 }}>
        <h3 style={{ marginBottom: 10 }}>Зафиксировать оплату</h3>
        <div className="form-row">
          <Field label="Сумма, ₽"><input type="number" value={amount}
                 onChange={(e) => setAmount(e.target.value)} /></Field>
          <Field label="Период с"><input type="date" value={start}
                 onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="по"><input type="date" value={end}
                 onChange={(e) => setEnd(e.target.value)} /></Field>
          <Field label="Оплачено"><input type="date" value={paidAt}
                 onChange={(e) => setPaidAt(e.target.value)} /></Field>
        </div>
        {error && <div className="error-text">{error}</div>}
        <button className="btn-primary" onClick={add} disabled={!amount}>Добавить</button>
        <p className="hint" style={{ marginTop: 8 }}>
          Оплата сдвигает дату следующего платежа и снимает grace/paused.
        </p>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Период</th><th>Сумма</th><th>Оплачено</th><th>Заметка</th></tr></thead>
          <tbody>
            {(salon.payments ?? []).map((p: any) => (
              <tr key={p.id}>
                <td>{dayjs(p.period_start).format("D MMM")} — {dayjs(p.period_end).format("D MMM YYYY")}</td>
                <td>{money(p.amount)}</td>
                <td>{p.paid_at ? dayjs(p.paid_at).format("D MMM YYYY") : <Badge value="failed" label="не оплачено" />}</td>
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
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  useEffect(() => setFlags({ ...(salon.feature_flags ?? {}) }), [salon]);

  const save = async () => {
    await api(`/api/admin/salons/${salon.id}`, {
      method: "PATCH", body: { feature_flags: flags },
    });
    onSaved();
  };

  return (
    <div style={{ maxWidth: 420 }}>
      {Object.entries(FLAG_LABELS).map(([key, label]) => (
        <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={Boolean(flags[key])}
                 onChange={(e) => setFlags({ ...flags, [key]: e.target.checked })} />
          {label}
        </label>
      ))}
      <button className="btn-primary" onClick={save}>Сохранить флаги</button>
      <p className="hint" style={{ marginTop: 8 }}>
        Флаги нужны, чтобы продавать пакеты и выкатывать новое на одном салоне.
      </p>
    </div>
  );
}

function SalonAudit({ salonId }: { salonId: number }) {
  const audit = useQuery({
    queryKey: ["salon-audit", salonId],
    queryFn: () => api(`/api/admin/audit?salon_id=${salonId}&page_size=100`),
  });
  if (audit.isLoading) return <Spinner />;
  const items = audit.data?.items ?? [];
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Объект</th><th /></tr></thead>
        <tbody>
          {items.map((a: any) => (
            <tr key={a.id}>
              <td>{dayjs(a.created_at).format("D MMM HH:mm")}</td>
              <td>{a.user_email ?? "система"}</td>
              <td>{a.action}{a.is_support && <> <Badge value="stub" label="поддержка" /></>}</td>
              <td>{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""}</td>
              <td className="hint" style={{ maxWidth: 300, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {a.after ? JSON.stringify(a.after) : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && <Empty />}
    </div>
  );
}

export default function SalonDetailPage() {
  const { id } = useParams();
  const salonId = Number(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const [tab, setTab] = useState("overview");
  const [inviteLink, setInviteLink] = useState("");
  const salon = useQuery({
    queryKey: ["salon", salonId],
    queryFn: () => api(`/api/admin/salons/${salonId}`),
  });

  const onSaved = () => {
    qc.invalidateQueries({ queryKey: ["salon", salonId] });
    qc.invalidateQueries({ queryKey: ["salons"] });
  };

  const impersonate = async () => {
    await api(`/api/admin/salons/${salonId}/impersonate`, { method: "POST" });
    await refresh();
    navigate("/");
  };

  const reinvite = async () => {
    const r = await api(`/api/admin/salons/${salonId}/invite`, { method: "POST" });
    setInviteLink(`${window.location.origin}${r.invite_link}`);
  };

  if (salon.isLoading) return <Spinner />;
  const s = salon.data;

  return (
    <>
      <div className="page-head">
        <h1>{s.name} <Badge value={s.status} label={SALON_STATUS_LABELS[s.status]} /></h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={reinvite}>🔗 Новое приглашение владельцу</button>
          <button className="btn-primary" onClick={impersonate}>🛠 Войти в режим поддержки</button>
        </div>
      </div>
      {inviteLink && (
        <div className="card">
          Ссылка-приглашение (72 ч): <span style={{ wordBreak: "break-all" }}>{inviteLink}</span>{" "}
          <button className="btn-sm" onClick={() => navigator.clipboard.writeText(inviteLink)}>📋</button>
        </div>
      )}
      <Tabs active={tab} onChange={setTab} tabs={[
        ["overview", "Обзор"], ["billing", "Биллинг"], ["flags", "Флаги"], ["audit", "Аудит"],
      ]} />
      {tab === "overview" && <Overview salon={s} onSaved={onSaved} />}
      {tab === "billing" && <Billing salon={s} onSaved={onSaved} />}
      {tab === "flags" && <Flags salon={s} onSaved={onSaved} />}
      {tab === "audit" && <SalonAudit salonId={salonId} />}
    </>
  );
}

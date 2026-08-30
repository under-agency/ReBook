import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { HoursEditor, ServicesEditor, StaffEditor, TextsEditor } from "../../components/editors";
import { Field, Spinner, Tabs } from "../../components/ui";

function ParamsEditor({ settings }: { settings: any }) {
  const qc = useQueryClient();
  // форма инициализируется один раз; пересоздание — через key у родителя
  const [name, setName] = useState(settings.name ?? "");
  const [avgCheck, setAvgCheck] = useState(String(settings.avg_check ?? ""));
  const [off1, setOff1] = useState(settings.remind_offsets_h?.[0] ?? 24);
  const [off2, setOff2] = useState(settings.remind_offsets_h?.[1] ?? 3);
  const [msg, setMsg] = useState("");

  const save = async () => {
    setMsg("");
    try {
      await api("/api/settings", {
        method: "PATCH",
        body: {
          name,
          avg_check: avgCheck ? Number(avgCheck) : null,
          remind_offsets_h: [Number(off1), Number(off2)],
        },
      });
      qc.invalidateQueries({ queryKey: ["settings"] });
      setMsg("Сохранено ✓");
    } catch (e) {
      setMsg(errorText(e));
    }
  };

  return (
    <div style={{ maxWidth: 480 }}>
      <Field label="Название салона">
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Средний чек, ₽ (для расчёта «возвращено N ₽»)">
        <input type="number" value={avgCheck} onChange={(e) => setAvgCheck(e.target.value)} />
      </Field>
      <div className="form-row">
        <Field label="Первое напоминание, часов до визита">
          <input type="number" value={off1} onChange={(e) => setOff1(Number(e.target.value))} />
        </Field>
        <Field label="Догон, часов до визита">
          <input type="number" value={off2} onChange={(e) => setOff2(Number(e.target.value))} />
        </Field>
      </div>
      <Field label="Лимит SMS в месяц (меняется через поддержку)">
        <input value={settings.sms_limit_month} disabled />
      </Field>
      {msg && <div className={msg.includes("✓") ? "hint" : "error-text"}>{msg}</div>}
      <button className="btn-primary" onClick={save}>Сохранить</button>
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState("services");
  const qc = useQueryClient();
  const { me } = useAuth();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/settings") });

  if (settings.isLoading) return <Spinner />;
  const s = settings.data;
  const salonKey = me?.salon?.id ?? 0;

  const saveHours = async (work_hours: any) => {
    await api("/api/settings", { method: "PATCH", body: { work_hours } });
    qc.invalidateQueries({ queryKey: ["settings"] });
  };
  const saveTexts = async (texts: any) => {
    await api("/api/settings", { method: "PATCH", body: { texts } });
    qc.invalidateQueries({ queryKey: ["settings"] });
  };

  return (
    <>
      <div className="page-head"><h1>Настройки</h1></div>
      <Tabs active={tab} onChange={setTab} tabs={[
        ["services", "Услуги"], ["staff", "Мастера"], ["hours", "Часы работы"],
        ["texts", "Тексты"], ["params", "Параметры"],
      ]} />
      {tab === "services" && <ServicesEditor />}
      {tab === "staff" && <StaffEditor />}
      {tab === "hours" && <HoursEditor key={salonKey} value={s.work_hours} onSave={saveHours} />}
      {tab === "texts" && <TextsEditor key={salonKey} value={s.texts} onSave={saveTexts} />}
      {tab === "params" && <ParamsEditor key={salonKey} settings={s} />}
    </>
  );
}

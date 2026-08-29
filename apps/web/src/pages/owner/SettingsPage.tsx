import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, errorText } from "../../api/client";
import { HoursEditor, ServicesEditor, StaffEditor, TextsEditor } from "../../components/editors";
import { Field, Spinner, Tabs } from "../../components/ui";

function ParamsEditor({ settings }: { settings: any }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [avgCheck, setAvgCheck] = useState("");
  const [off1, setOff1] = useState(24);
  const [off2, setOff2] = useState(3);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setName(settings.name ?? "");
    setAvgCheck(String(settings.avg_check ?? ""));
    setOff1(settings.remind_offsets_h?.[0] ?? 24);
    setOff2(settings.remind_offsets_h?.[1] ?? 3);
  }, [settings]);

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
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/settings") });

  if (settings.isLoading) return <Spinner />;
  const s = settings.data;

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
      {tab === "hours" && <HoursEditor value={s.work_hours} onSave={saveHours} />}
      {tab === "texts" && <TextsEditor value={s.texts} onSave={saveTexts} />}
      {tab === "params" && <ParamsEditor settings={s} />}
    </>
  );
}

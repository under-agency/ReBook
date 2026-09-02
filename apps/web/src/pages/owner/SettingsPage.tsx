import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { HoursEditor, ServicesEditor, StaffEditor, TextsEditor } from "../../components/editors";
import { useToast } from "../../components/toast";
import { Button, Field, LoadError, Skeleton, Tabs } from "../../components/ui";

function ParamsEditor({ settings }: { settings: any }) {
  const qc = useQueryClient();
  const toast = useToast();
  // форма инициализируется один раз; пересоздание — через key у родителя
  const [name, setName] = useState(settings.name ?? "");
  const [avgCheck, setAvgCheck] = useState(String(settings.avg_check ?? ""));
  const [off1, setOff1] = useState(settings.remind_offsets_h?.[0] ?? 24);
  const [off2, setOff2] = useState(settings.remind_offsets_h?.[1] ?? 3);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
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
      toast.ok("Параметры сохранены");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="narrow">
      <Field label="Название салона">
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Средний чек, ₽ — из него считается «возвращено ≈ N ₽»">
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
      <Field label="Лимит SMS в месяц — меняется через поддержку">
        <input value={settings.sms_limit_month} disabled />
      </Field>
      <Button variant="primary" disabled={busy} onClick={save}>
        {busy ? "Сохраняем…" : "Сохранить"}
      </Button>
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState("services");
  const qc = useQueryClient();
  const toast = useToast();
  const { me } = useAuth();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<any>("/api/settings") });

  if (settings.isError) return <LoadError onRetry={() => settings.refetch()} />;
  if (settings.isLoading || !settings.data) {
    return (
      <div className="stack">
        <Skeleton w="40%" h={16} /><Skeleton w="100%" h={30} /><Skeleton w="100%" h={30} />
      </div>
    );
  }

  const s = settings.data;
  const salonKey = me?.salon?.id ?? 0;

  const patch = (body: any, done: string) => async () => {
    try {
      await api("/api/settings", { method: "PATCH", body });
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.ok(done);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const saveHours = (work_hours: any) => patch({ work_hours }, "Часы работы сохранены")();
  const saveTexts = (texts: any) => patch({ texts }, "Тексты сообщений сохранены")();

  return (
    <>
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

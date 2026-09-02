import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Bell, Check, ChevronLeft } from "lucide-react";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { HoursEditor, ServicesEditor, StaffEditor, TextsEditor } from "../../components/editors";
import { useToast } from "../../components/toast";
import { Button, LoadError, Skeleton } from "../../components/ui";

const STEPS = ["Услуги", "Мастера и часы", "Тексты", "Проверка"];

export default function OnboardingWizard() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");
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

  const next = async () => {
    setError("");
    try {
      await api("/api/onboarding/step", { method: "POST", body: { step: step + 1 } });
      setStep(step + 1);
    } catch (e) {
      setError(errorText(e));
    }
  };

  const complete = async () => {
    setError("");
    try {
      await api("/api/onboarding/complete", { method: "POST" });
      await refresh();
      toast.ok("Настройка завершена — напоминания включены");
      navigate("/");
    } catch (e) {
      setError(errorText(e));
    }
  };

  const sendTest = async () => {
    setError("");
    setTestResult("");
    try {
      const r = await api<any>("/api/settings/test-reminder", { method: "POST" });
      setTestResult(r.preview);
      toast.ok("Тестовое напоминание отправлено");
    } catch (e) {
      setError(errorText(e));
    }
  };

  const saveHours = async (work_hours: any) => {
    await api("/api/settings", { method: "PATCH", body: { work_hours } });
    qc.invalidateQueries({ queryKey: ["settings"] });
    toast.ok("Часы работы сохранены");
  };
  const saveTexts = async (texts: any) => {
    await api("/api/settings", { method: "PATCH", body: { texts } });
    qc.invalidateQueries({ queryKey: ["settings"] });
    toast.ok("Тексты сохранены");
  };

  return (
    <>
      <div className="section-head"><h1>Настройка салона «{s.name}»</h1></div>
      <p className="hint mb-4">
        Пока настройка не завершена, рассылки клиентам не идут, а бот отвечает
        «запись скоро откроется».
      </p>

      <div className="wizard-steps">
        {STEPS.map((label, i) => (
          <div key={label}
               className={"wstep" + (i === step ? " wstep-active" : i < step ? " wstep-done" : "")}>
            {i + 1}. {label}
          </div>
        ))}
      </div>

      <div className="card">
        {step === 0 && (
          <>
            <p className="hint mb-3">
              Заготовки услуг под вашу нишу уже добавлены — поправьте цены и циклы повтора
              под себя.
            </p>
            <ServicesEditor />
          </>
        )}
        {step === 1 && (
          <>
            <h2 className="mb-3">Мастера</h2>
            <StaffEditor />
            <h2 className="mt-4 mb-3">Часы работы</h2>
            <HoursEditor value={s.work_hours} onSave={saveHours} />
          </>
        )}
        {step === 2 && <TextsEditor value={s.texts} onSave={saveTexts} />}
        {step === 3 && (
          <>
            <p className="mb-3">
              Отправьте себе тестовое напоминание — увидите ровно то, что получат ваши клиенты.
            </p>
            <p className="hint mb-3">
              Сначала напишите вашему боту в Telegram команду <span className="mono">/admin</span> —
              он привяжет ваш чат для служебных сообщений.
            </p>
            <Button onClick={sendTest}><Bell size={14} /> Отправить тестовое напоминание</Button>
            {testResult && (
              <div className="msg-item mt-3">
                <div className="msg-meta">Так это увидит клиент</div>
                {testResult}
              </div>
            )}
          </>
        )}
      </div>

      {error && <div className="error-text">{error}</div>}
      <div className="row">
        {step > 0 && (
          <Button onClick={() => setStep(step - 1)}><ChevronLeft size={14} /> Назад</Button>
        )}
        {step < 3 && (
          <Button variant="primary" onClick={next}>Дальше <ArrowRight size={14} /></Button>
        )}
        {step === 3 && (
          <Button variant="primary" onClick={complete}>
            <Check size={14} /> Завершить настройку и включить напоминания
          </Button>
        )}
      </div>
    </>
  );
}

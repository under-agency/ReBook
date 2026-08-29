import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { HoursEditor, ServicesEditor, StaffEditor, TextsEditor } from "../../components/editors";
import { Spinner } from "../../components/ui";

const STEPS = ["Услуги", "Мастера и часы", "Тексты", "Проверка"];

export default function OnboardingWizard() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/settings") });

  if (settings.isLoading) return <Spinner />;
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
      navigate("/");
    } catch (e) {
      setError(errorText(e));
    }
  };

  const sendTest = async () => {
    setError("");
    setTestResult("");
    try {
      const r = await api("/api/settings/test-reminder", { method: "POST" });
      setTestResult("Отправлено! Проверьте мессенджер. Текст: " + r.preview);
    } catch (e) {
      setError(errorText(e));
    }
  };

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
      <h1>Настройка салона «{s.name}»</h1>
      <p className="hint" style={{ marginBottom: 16 }}>
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
            <p className="hint" style={{ marginBottom: 12 }}>
              Мы подготовили заготовки услуг под вашу нишу — поправьте цены и циклы под себя.
            </p>
            <ServicesEditor />
          </>
        )}
        {step === 1 && (
          <>
            <h2 style={{ marginTop: 0 }}>Мастера</h2>
            <StaffEditor />
            <h2>Часы работы</h2>
            <HoursEditor value={s.work_hours} onSave={saveHours} />
          </>
        )}
        {step === 2 && <TextsEditor value={s.texts} onSave={saveTexts} />}
        {step === 3 && (
          <>
            <p style={{ marginBottom: 12 }}>
              Отправьте себе тестовое напоминание — вы увидите ровно то, что будут
              получать ваши клиенты.
            </p>
            <p className="hint" style={{ marginBottom: 12 }}>
              Для этого напишите вашему боту в Telegram команду <b>/admin</b> —
              он привяжет ваш чат для служебных сообщений.
            </p>
            <button onClick={sendTest}>🔔 Отправить тестовое напоминание себе</button>
            {testResult && <p className="hint" style={{ marginTop: 10 }}>{testResult}</p>}
          </>
        )}
      </div>

      {error && <div className="error-text">{error}</div>}
      <div style={{ display: "flex", gap: 10 }}>
        {step > 0 && <button onClick={() => setStep(step - 1)}>← Назад</button>}
        {step < 3 && <button className="btn-primary" onClick={next}>Дальше →</button>}
        {step === 3 && (
          <button className="btn-primary" onClick={complete}>
            ✅ Завершить настройку и включить рассылки
          </button>
        )}
      </div>
    </>
  );
}

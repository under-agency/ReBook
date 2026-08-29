import { FormEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errorText } from "../api/client";
import { Me, useAuth } from "../auth/AuthContext";
import { Field } from "../components/ui";

export default function InvitePage() {
  const { token } = useParams();
  const { setMe } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== password2) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const me = await api<Me>("/api/auth/accept-invite", {
        method: "POST",
        body: { token, password },
      });
      setMe(me);
      navigate("/");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="logo">Re<span style={{ color: "var(--accent)" }}>Book</span></div>
        <p style={{ marginBottom: 16, color: "var(--muted)" }}>
          Добро пожаловать! Придумайте пароль для входа в кабинет.
        </p>
        <Field label="Пароль (от 8 символов)">
          <input type="password" value={password} minLength={8}
                 onChange={(e) => setPassword(e.target.value)} required autoFocus />
        </Field>
        <Field label="Пароль ещё раз">
          <input type="password" value={password2}
                 onChange={(e) => setPassword2(e.target.value)} required />
        </Field>
        {error && <div className="error-text">{error}</div>}
        <button className="btn-primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Сохраняем…" : "Задать пароль и войти"}
        </button>
      </form>
    </div>
  );
}

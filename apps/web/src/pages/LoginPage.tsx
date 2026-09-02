import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText } from "../api/client";
import { Me, useAuth } from "../auth/AuthContext";
import { Button, Field } from "../components/ui";

export default function LoginPage() {
  const { setMe } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = await api<Me>("/api/auth/login", {
        method: "POST",
        body: { email, password },
      });
      setMe(me);
      navigate(me.salon ? "/" : "/admin");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="logo">Re<span>Book</span></div>
        <Field label="Email">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 required autoFocus />
        </Field>
        <Field label="Пароль">
          <input type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {error && <div className="error-text">{error}</div>}
        <Button type="submit" variant="primary" className="btn-block" disabled={busy}>
          {busy ? "Входим…" : "Войти"}
        </Button>
      </form>
    </div>
  );
}

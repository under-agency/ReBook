import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../../api/client";
import { Field } from "../../components/ui";

export default function SalonNewPage() {
  const niches = useQuery({ queryKey: ["niches"], queryFn: () => api("/api/admin/niches") });
  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [tgToken, setTgToken] = useState("");
  const [avgCheck, setAvgCheck] = useState("");
  const [smsLimit, setSmsLimit] = useState(300);
  const [monthlyFee, setMonthlyFee] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api("/api/admin/salons", {
        method: "POST",
        body: {
          name, niche: niche || null, owner_email: ownerEmail,
          tg_bot_token: tgToken || null,
          avg_check: avgCheck ? Number(avgCheck) : null,
          sms_limit_month: Number(smsLimit),
          monthly_fee: monthlyFee ? Number(monthlyFee) : null,
        },
      });
      setResult(r);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const link = `${window.location.origin}${result.invite_link}`;
    return (
      <div className="card" style={{ maxWidth: 560 }}>
        <h2 style={{ marginTop: 0 }}>✅ Салон «{result.salon.name}» создан</h2>
        <p style={{ marginBottom: 10 }}>
          Отправьте владельцу ({result.owner_email}) ссылку-приглашение
          (действует 72 часа):
        </p>
        <div className="msg-item" style={{ wordBreak: "break-all", marginBottom: 14 }}>{link}</div>
        <button onClick={() => navigator.clipboard.writeText(link)}>📋 Скопировать</button>{" "}
        <Link to={`/admin/salons/${result.salon.id}`}><button>К карточке салона</button></Link>
      </div>
    );
  }

  return (
    <form className="card" style={{ maxWidth: 560 }} onSubmit={submit}>
      <h1 style={{ marginBottom: 18 }}>Новый салон</h1>
      <Field label="Название">
        <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      </Field>
      <div className="form-row">
        <Field label="Ниша (подтянет заготовки услуг)">
          <select value={niche} onChange={(e) => setNiche(e.target.value)}>
            <option value="">Без заготовок</option>
            {(niches.data?.niches ?? []).map((n: any) => (
              <option key={n.key} value={n.key}>{n.key}</option>
            ))}
          </select>
        </Field>
        <Field label="Email владельца">
          <input type="email" value={ownerEmail}
                 onChange={(e) => setOwnerEmail(e.target.value)} required />
        </Field>
      </div>
      <Field label="Токен Telegram-бота (@BotFather)">
        <input value={tgToken} onChange={(e) => setTgToken(e.target.value)}
               placeholder="123456:ABC-DEF…" />
      </Field>
      <div className="form-row">
        <Field label="Средний чек, ₽">
          <input type="number" value={avgCheck} onChange={(e) => setAvgCheck(e.target.value)} />
        </Field>
        <Field label="Лимит SMS/мес">
          <input type="number" value={smsLimit}
                 onChange={(e) => setSmsLimit(Number(e.target.value))} />
        </Field>
        <Field label="Абонентка, ₽/мес">
          <input type="number" value={monthlyFee}
                 onChange={(e) => setMonthlyFee(e.target.value)} />
        </Field>
      </div>
      {error && <div className="error-text">{error}</div>}
      <button className="btn-primary" disabled={busy}>
        {busy ? "Создаём…" : "Создать салон и пригласить владельца"}
      </button>
    </form>
  );
}

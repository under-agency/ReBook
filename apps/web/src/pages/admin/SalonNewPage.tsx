import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy } from "lucide-react";
import { api, errorText } from "../../api/client";
import { useToast } from "../../components/toast";
import { Button, Field } from "../../components/ui";

export default function SalonNewPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const niches = useQuery({ queryKey: ["niches"], queryFn: () => api<any>("/api/admin/niches") });
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
      const r = await api<any>("/api/admin/salons", {
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
      toast.ok(`Салон «${r.salon.name}» создан`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const link = `${window.location.origin}${result.invite_link}`;
    const copy = async () => {
      try {
        await navigator.clipboard.writeText(link);
        toast.ok("Ссылка скопирована");
      } catch {
        toast.error("Браузер не дал доступ к буферу — скопируйте вручную");
      }
    };
    return (
      <div className="card narrow">
        <h2 className="mb-3">Салон «{result.salon.name}» создан</h2>
        <p className="mb-3">
          Отправьте владельцу (<span className="mono">{result.owner_email}</span>)
          ссылку-приглашение. Она действует 72 часа.
        </p>
        <div className="msg-item mb-3" style={{ wordBreak: "break-all" }}>
          <span className="mono">{link}</span>
        </div>
        <div className="row">
          <Button onClick={copy}><Copy size={14} /> Скопировать ссылку</Button>
          <Button variant="primary"
                  onClick={() => navigate(`/admin/salons/${result.salon.id}`)}>
            К карточке салона
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <Field label="Название">
        <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      </Field>
      <div className="form-row">
        <Field label="Ниша — подтянет заготовки услуг">
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
      <Field label="Токен Telegram-бота из @BotFather">
        <input value={tgToken} onChange={(e) => setTgToken(e.target.value)}
               placeholder="123456:ABC-DEF…" />
      </Field>
      <div className="form-row">
        <Field label="Средний чек, ₽">
          <input type="number" value={avgCheck} onChange={(e) => setAvgCheck(e.target.value)} />
        </Field>
        <Field label="Лимит SMS в месяц">
          <input type="number" value={smsLimit}
                 onChange={(e) => setSmsLimit(Number(e.target.value))} />
        </Field>
        <Field label="Абонентка, ₽/мес">
          <input type="number" value={monthlyFee}
                 onChange={(e) => setMonthlyFee(e.target.value)} />
        </Field>
      </div>
      {error && <div className="error-text">{error}</div>}
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Создаём…" : "Создать салон и пригласить владельца"}
      </Button>
    </form>
  );
}

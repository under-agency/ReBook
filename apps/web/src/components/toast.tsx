import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import { Check, TriangleAlert } from "lucide-react";

type Kind = "ok" | "error";
type Item = { id: number; kind: Kind; text: string };

const Ctx = createContext<{
  ok: (text: string) => void;
  error: (text: string) => void;
}>({ ok: () => {}, error: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const seq = useRef(0);

  const push = useCallback((kind: Kind, text: string) => {
    const id = ++seq.current;
    setItems((prev) => [...prev, { id, kind, text }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, kind === "error" ? 7000 : 3500);
  }, []);

  const ok = useCallback((text: string) => push("ok", text), [push]);
  const error = useCallback((text: string) => push("error", text), [push]);

  return (
    <Ctx.Provider value={{ ok, error }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={"toast" + (t.kind === "error" ? " toast-error" : "")}>
            <span className="toast-icon">
              {t.kind === "error" ? <TriangleAlert size={15} /> : <Check size={15} />}
            </span>
            <span className="toast-text">{t.text}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);

import { ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, Building2, CalendarDays, Check, LayoutList, LogOut, Menu, MessageSquare,
  Monitor, Moon, ScrollText, Settings, Sun, Users, Wrench, X,
} from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useTheme, type Theme } from "../theme/ThemeContext";
import { Button } from "./ui";

/** Действия страницы уезжают в топбар — один заголовок на всё приложение. */
export function PageActions({ children }: { children: ReactNode }) {
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => setHost(document.getElementById("page-actions")), []);
  return host ? createPortal(children, host) : null;
}

const TITLES: [RegExp, string][] = [
  [/^\/$/, "Сегодня"],
  [/^\/bookings/, "Записи"],
  [/^\/customers/, "Клиенты"],
  [/^\/messages/, "Сообщения"],
  [/^\/reports/, "Отчёты"],
  [/^\/audit/, "Журнал изменений"],
  [/^\/settings/, "Настройки"],
  [/^\/onboarding/, "Настройка салона"],
  [/^\/admin\/salons\/new/, "Новый салон"],
  [/^\/admin\/salons\//, "Салон"],
  [/^\/admin\/logs/, "Журналы"],
  [/^\/admin/, "Салоны"],
];

const THEME_OPTIONS: [Theme, string, typeof Sun][] = [
  ["light", "Светлая", Sun],
  ["dark", "Тёмная", Moon],
  ["system", "Как в системе", Monitor],
];

function UserMenu() {
  const { me, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const doLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="menu-wrap" ref={wrap}>
      <Button variant="ghost" size="sm" onClick={() => setOpen(!open)}
              aria-haspopup="menu" aria-expanded={open}>
        {me?.user.email}
      </Button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-label">Тема</div>
          {THEME_OPTIONS.map(([value, label, Icon]) => (
            <button key={value} role="menuitemradio" aria-checked={theme === value}
                    onClick={() => { setTheme(value); setOpen(false); }}>
              <Icon size={14} />
              {label}
              {theme === value && <Check size={14} className="push" />}
            </button>
          ))}
          <div className="menu-sep" />
          <button role="menuitem" onClick={doLogout}>
            <LogOut size={14} /> Выйти
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  // Переход по ссылке на узком экране закрывает выдвижное меню
  useEffect(() => setNavOpen(false), [pathname]);

  if (!me) return null;

  const role = me.user.role;
  const inSalon = me.salon !== null;
  const title = TITLES.find(([re]) => re.test(pathname))?.[1] ?? "ReBook";

  const stopSupport = async () => {
    await api("/api/admin/impersonate/stop", { method: "POST" });
    await refresh();
    navigate("/admin");
  };

  return (
    <div className="layout">
      {navOpen && <div className="sidebar-scrim" onClick={() => setNavOpen(false)} />}
      <aside className={"sidebar" + (navOpen ? " sidebar-open" : "")}>
        <div className="logo">
          Re<span>Book</span>
          <Button variant="ghost" size="sm" icon className="push topbar-burger"
                  onClick={() => setNavOpen(false)} aria-label="Закрыть меню">
            <X size={15} />
          </Button>
        </div>
        <nav aria-label="Основная навигация">
          {inSalon && (
            <>
              <NavLink to="/" end><LayoutList size={15} /> Сегодня</NavLink>
              <NavLink to="/bookings"><CalendarDays size={15} /> Записи</NavLink>
              <NavLink to="/customers"><Users size={15} /> Клиенты</NavLink>
              <NavLink to="/messages"><MessageSquare size={15} /> Сообщения</NavLink>
              {role !== "staff" && (
                <>
                  <NavLink to="/reports"><BarChart3 size={15} /> Отчёты</NavLink>
                  <NavLink to="/audit"><ScrollText size={15} /> Журнал изменений</NavLink>
                  <NavLink to="/settings"><Settings size={15} /> Настройки</NavLink>
                </>
              )}
            </>
          )}
          {role === "superadmin" && (
            <>
              <div className="nav-sep">Админка</div>
              <NavLink to="/admin" end><Building2 size={15} /> Салоны</NavLink>
              <NavLink to="/admin/logs"><ScrollText size={15} /> Журналы</NavLink>
            </>
          )}
        </nav>
        {me.salon && (
          <div className="sidebar-foot">
            <div className="hint t-trunc" title={me.salon.name}>{me.salon.name}</div>
          </div>
        )}
      </aside>

      <div className="content-wrap">
        <div className="topbar">
          <Button variant="ghost" size="sm" icon className="topbar-burger"
                  onClick={() => setNavOpen(true)} aria-label="Открыть меню">
            <Menu size={16} />
          </Button>
          <span className="topbar-title">{title}</span>
          <div className="topbar-actions">
            <div id="page-actions" className="row" />
            <UserMenu />
          </div>
        </div>

        {me.is_support && me.salon && (
          <div className="support-banner">
            <Wrench size={14} />
            Режим поддержки: <b>{me.salon.name}</b> — все действия попадают в аудит салона
            <button className="link-btn push" onClick={stopSupport}>Выйти из режима</button>
          </div>
        )}
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

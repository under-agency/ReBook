import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { me, refresh, logout } = useAuth();
  const navigate = useNavigate();
  if (!me) return null;

  const role = me.user.role;
  const inSalon = me.salon !== null;

  const stopSupport = async () => {
    await api("/api/admin/impersonate/stop", { method: "POST" });
    await refresh();
    navigate("/admin");
  };

  const doLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">Re<span>Book</span></div>
        <nav>
          {inSalon && (
            <>
              <NavLink to="/" end>📊 Дашборд</NavLink>
              <NavLink to="/bookings">📅 Записи</NavLink>
              <NavLink to="/customers">👥 Клиенты</NavLink>
              <NavLink to="/messages">✉️ Сообщения</NavLink>
              {role !== "staff" && <NavLink to="/reports">📈 Отчёты</NavLink>}
              {role !== "staff" && <NavLink to="/settings">⚙️ Настройки</NavLink>}
            </>
          )}
          {role === "superadmin" && (
            <>
              <div className="nav-sep">Админка</div>
              <NavLink to="/admin" end>🏢 Салоны</NavLink>
              <NavLink to="/admin/logs">🗒 Журналы</NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-foot">
          <div className="user-email" title={me.user.email}>{me.user.email}</div>
          <button className="link-btn" onClick={doLogout}>Выйти</button>
        </div>
      </aside>
      <div className="content-wrap">
        {me.is_support && me.salon && (
          <div className="support-banner">
            🛠 Режим поддержки: <b>{me.salon.name}</b> — все действия попадают в аудит салона
            <button className="link-btn" onClick={stopSupport}>Выйти из режима</button>
          </div>
        )}
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

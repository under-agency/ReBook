import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import LoginPage from "./pages/LoginPage";
import InvitePage from "./pages/InvitePage";
import DashboardPage from "./pages/owner/DashboardPage";
import BookingsPage from "./pages/owner/BookingsPage";
import CustomersPage from "./pages/owner/CustomersPage";
import MessagesPage from "./pages/owner/MessagesPage";
import ReportsPage from "./pages/owner/ReportsPage";
import SettingsPage from "./pages/owner/SettingsPage";
import OnboardingWizard from "./pages/owner/OnboardingWizard";
import SalonsListPage from "./pages/admin/SalonsListPage";
import SalonNewPage from "./pages/admin/SalonNewPage";
import SalonDetailPage from "./pages/admin/SalonDetailPage";
import AdminLogsPage from "./pages/admin/AdminLogsPage";

export default function App() {
  const { me, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;

  if (!me) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  const role = me.user.role;
  const inSalon = me.salon !== null;

  // владелец не прошёл мастер → принудительно в онбординг
  const needsOnboarding =
    role === "owner" && me.salon?.status === "onboarding";
  if (needsOnboarding && location.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }

  return (
    <Layout>
      <Routes>
        {inSalon && (
          <>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/bookings" element={<BookingsPage />} />
            <Route path="/customers" element={<CustomersPage />} />
            <Route path="/messages" element={<MessagesPage />} />
            {role !== "staff" && (
              <>
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/reports/:month" element={<ReportsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/onboarding" element={<OnboardingWizard />} />
              </>
            )}
          </>
        )}
        {role === "superadmin" && (
          <>
            <Route path="/admin" element={<SalonsListPage />} />
            <Route path="/admin/salons/new" element={<SalonNewPage />} />
            <Route path="/admin/salons/:id" element={<SalonDetailPage />} />
            <Route path="/admin/logs" element={<AdminLogsPage />} />
            {!inSalon && <Route path="/" element={<Navigate to="/admin" replace />} />}
          </>
        )}
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to={inSalon ? "/" : "/admin"} replace />} />
      </Routes>
    </Layout>
  );
}

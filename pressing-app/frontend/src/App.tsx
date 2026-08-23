import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RequirePermission } from "@/components/RequirePermission";
import { useAuth } from "@/contexts/AuthContext";
import { landingRouteForRole } from "@/lib/roles";
import LoginPage from "@/pages/LoginPage";
import TrackOrderPage from "@/pages/TrackOrderPage";
import DashboardPage from "@/pages/DashboardPage";
import CashierWorkspacePage from "@/pages/workspace/CashierWorkspacePage";
import OperatorWorkspacePage from "@/pages/workspace/OperatorWorkspacePage";
import DeliveryWorkspacePage from "@/pages/workspace/DeliveryWorkspacePage";
import CustomersPage from "@/pages/CustomersPage";
import CustomerDetailPage from "@/pages/CustomerDetailPage";
import ServicesPage from "@/pages/ServicesPage";
import OrdersPage from "@/pages/OrdersPage";
import NewOrderPage from "@/pages/NewOrderPage";
import OrderDetailPage from "@/pages/OrderDetailPage";
import DeliveriesPage from "@/pages/DeliveriesPage";
import CashRegisterPage from "@/pages/CashRegisterPage";
import ExpensesPage from "@/pages/ExpensesPage";
import InventoryPage from "@/pages/InventoryPage";
import EmployeesPage from "@/pages/EmployeesPage";
import BranchesPage from "@/pages/BranchesPage";
import ReportsPage from "@/pages/ReportsPage";
import SettingsPage from "@/pages/SettingsPage";
import NotFoundPage from "@/pages/NotFoundPage";
import { PortalProtectedRoute } from "@/components/PortalProtectedRoute";
import { PortalLayout } from "@/components/layout/PortalLayout";
import PortalLoginPage from "@/pages/portal/PortalLoginPage";
import PortalRegisterPage from "@/pages/portal/PortalRegisterPage";
import PortalOrdersPage from "@/pages/portal/PortalOrdersPage";
import PortalNewOrderPage from "@/pages/portal/PortalNewOrderPage";
import PortalOrderDetailPage from "@/pages/portal/PortalOrderDetailPage";

/**
 * "/" is the Dashboard for management roles, but CASHIER/OPERATOR/DELIVERY
 * no longer carry dashboard:read (see backend/src/lib/permissions.ts) — for
 * them this redirects straight to their Workspace instead of rendering a
 * Dashboard that would just 403 against the API.
 */
function RoleHome() {
  const { user, hasPermission } = useAuth();
  if (user && !hasPermission("dashboard:read")) {
    return <Navigate to={landingRouteForRole(user.role)} replace />;
  }
  return <DashboardPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/track" element={<TrackOrderPage />} />
      <Route path="/portal/login" element={<PortalLoginPage />} />
      <Route path="/portal/register" element={<PortalRegisterPage />} />

      <Route
        element={
          <PortalProtectedRoute>
            <PortalLayout />
          </PortalProtectedRoute>
        }
      >
        <Route path="/portal/orders" element={<PortalOrdersPage />} />
        <Route path="/portal/orders/new" element={<PortalNewOrderPage />} />
        <Route path="/portal/orders/:id" element={<PortalOrderDetailPage />} />
      </Route>

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<RoleHome />} />
        <Route path="/workspace/cashier" element={<CashierWorkspacePage />} />
        <Route path="/workspace/operator" element={<OperatorWorkspacePage />} />
        <Route path="/workspace/delivery" element={<DeliveryWorkspacePage />} />
        <Route
          path="/customers"
          element={
            <RequirePermission permission="customers:read">
              <CustomersPage />
            </RequirePermission>
          }
        />
        <Route
          path="/customers/:id"
          element={
            <RequirePermission permission="customers:read">
              <CustomerDetailPage />
            </RequirePermission>
          }
        />
        <Route
          path="/services"
          element={
            <RequirePermission permission="services:read">
              <ServicesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/orders"
          element={
            <RequirePermission permission="orders:read">
              <OrdersPage />
            </RequirePermission>
          }
        />
        <Route
          path="/orders/new"
          element={
            <RequirePermission permission="orders:write">
              <NewOrderPage />
            </RequirePermission>
          }
        />
        <Route
          path="/orders/:id"
          element={
            <RequirePermission permission="orders:read">
              <OrderDetailPage />
            </RequirePermission>
          }
        />
        <Route
          path="/deliveries"
          element={
            <RequirePermission permission="deliveries:read">
              <DeliveriesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/cash-register"
          element={
            <RequirePermission permission="cash:read">
              <CashRegisterPage />
            </RequirePermission>
          }
        />
        <Route
          path="/expenses"
          element={
            <RequirePermission permission="expenses:read">
              <ExpensesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/inventory"
          element={
            <RequirePermission permission="inventory:read">
              <InventoryPage />
            </RequirePermission>
          }
        />
        <Route
          path="/employees"
          element={
            <RequirePermission permission="employees:read">
              <EmployeesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/branches"
          element={
            <RequirePermission permission="branches:manage">
              <BranchesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/reports"
          element={
            <RequirePermission permission="reports:read">
              <ReportsPage />
            </RequirePermission>
          }
        />
        <Route
          path="/settings"
          element={
            <RequirePermission permission="settings:read">
              <SettingsPage />
            </RequirePermission>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

import { Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
import TrackOrderPage from "@/pages/TrackOrderPage";
import DashboardPage from "@/pages/DashboardPage";
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
        <Route path="/" element={<DashboardPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/new" element={<NewOrderPage />} />
        <Route path="/orders/:id" element={<OrderDetailPage />} />
        <Route path="/deliveries" element={<DeliveriesPage />} />
        <Route path="/cash-register" element={<CashRegisterPage />} />
        <Route path="/expenses" element={<ExpensesPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/employees" element={<EmployeesPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

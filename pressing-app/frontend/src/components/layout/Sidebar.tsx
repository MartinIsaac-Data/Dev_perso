import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  ShoppingBag,
  Users,
  Shirt,
  Truck,
  Wallet,
  Receipt,
  Boxes,
  UserCog,
  BarChart3,
  Settings,
  Building2,
  ClipboardList,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Logo } from "@/components/Logo";
import { useAuth } from "@/contexts/AuthContext";
import type { Role } from "@/types";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  permission?: string;
  /** Restricts an entry to specific roles regardless of permission — used for the Workspace home pages, which are role-specific rather than permission-gated features. */
  roles?: Role[];
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, permission: "dashboard:read" },
  { to: "/workspace/cashier", label: "Espace caissier", icon: Wallet, roles: ["CASHIER"] },
  { to: "/workspace/operator", label: "Espace atelier", icon: ClipboardList, roles: ["OPERATOR"] },
  { to: "/workspace/delivery", label: "Mes livraisons", icon: Truck, roles: ["DELIVERY"] },
  { to: "/orders", label: "Commandes", icon: ShoppingBag, permission: "orders:read" },
  { to: "/customers", label: "Clients", icon: Users, permission: "customers:read" },
  { to: "/services", label: "Services", icon: Shirt, permission: "services:read" },
  { to: "/deliveries", label: "Livraisons", icon: Truck, permission: "deliveries:read" },
  { to: "/cash-register", label: "Caisse", icon: Wallet, permission: "cash:read" },
  { to: "/expenses", label: "Dépenses", icon: Receipt, permission: "expenses:read" },
  { to: "/inventory", label: "Stock", icon: Boxes, permission: "inventory:read" },
  { to: "/employees", label: "Employés", icon: UserCog, permission: "employees:read" },
  { to: "/branches", label: "Agences", icon: Building2, permission: "branches:manage" },
  { to: "/reports", label: "Rapports", icon: BarChart3, permission: "reports:read" },
  { to: "/settings", label: "Paramètres", icon: Settings, permission: "settings:read" },
];

export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const { user, hasPermission } = useAuth();

  const content = (
    <nav className="flex h-full flex-col gap-1 overflow-y-auto p-3">
      <div className="mb-3 flex items-center justify-between px-2">
        <Logo size="sm" />
        <button onClick={onClose} className="rounded p-1 hover:bg-accent lg:hidden" aria-label="Fermer le menu">
          <X className="h-4 w-4" />
        </button>
      </div>
      {NAV.filter((item) => {
        if (item.roles && (!user || !item.roles.includes(user.role))) return false;
        if (item.permission && !hasPermission(item.permission)) return false;
        return true;
      }).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onClose}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-accent"
            )
          }
        >
          <item.icon className="h-4 w-4 shrink-0" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-border bg-card lg:block">{content}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={onClose} />
          <aside className="absolute left-0 top-0 h-full w-64 bg-card shadow-lg">{content}</aside>
        </div>
      )}
    </>
  );
}

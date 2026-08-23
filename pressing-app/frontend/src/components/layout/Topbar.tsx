import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, Moon, Sun, Search, LogOut, ChevronRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/hooks/useTheme";
import { Button } from "@/components/ui/button";
import { BranchSwitcher } from "./BranchSwitcher";

const LABELS: Record<string, string> = {
  "": "Dashboard",
  orders: "Commandes",
  customers: "Clients",
  services: "Services",
  deliveries: "Livraisons",
  "cash-register": "Caisse",
  expenses: "Dépenses",
  inventory: "Stock",
  employees: "Employés",
  branches: "Agences",
  reports: "Rapports",
  settings: "Paramètres",
};

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const segments = location.pathname.split("/").filter(Boolean);
  const crumbs = [{ label: LABELS[""] ?? "Dashboard", to: "/" }, ...segments.map((seg, i) => ({
    label: LABELS[seg] ?? seg,
    to: "/" + segments.slice(0, i + 1).join("/"),
  }))];

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-3">
        <button onClick={onMenuClick} className="rounded p-1.5 hover:bg-accent lg:hidden" aria-label="Menu">
          <Menu className="h-5 w-5" />
        </button>
        <nav className="hidden items-center gap-1 text-sm text-muted-foreground sm:flex">
          {crumbs.map((c, i) => (
            <span key={c.to} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5" />}
              {i === crumbs.length - 1 ? (
                <span className="font-medium text-foreground">{c.label}</span>
              ) : (
                <Link to={c.to} className="hover:text-foreground">
                  {c.label}
                </Link>
              )}
            </span>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-2">
        <BranchSwitcher />

        <button
          className="hidden items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground sm:flex"
          onClick={() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
        >
          <Search className="h-3.5 w-3.5" /> Rechercher
          <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px]">Ctrl K</kbd>
        </button>

        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Changer de thème">
          {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </Button>

        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
              {user?.fullName?.slice(0, 2).toUpperCase()}
            </div>
            <span className="hidden text-sm font-medium sm:inline">{user?.fullName}</span>
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-30 mt-1 w-48 rounded-md border border-border bg-card p-1 shadow-lg">
              <div className="px-2 py-1.5 text-xs text-muted-foreground">{user?.role}</div>
              <button
                onClick={logout}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent"
              >
                <LogOut className="h-4 w-4" /> Déconnexion
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

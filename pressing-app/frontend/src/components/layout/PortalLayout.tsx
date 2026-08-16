import { NavLink, Outlet } from "react-router-dom";
import { LogOut, Plus, Shirt } from "lucide-react";
import { usePortalAuth } from "@/contexts/PortalAuthContext";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function PortalLayout() {
  const { customer, logout } = usePortalAuth();

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-3xl items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Shirt className="h-4 w-4" />
            </div>
            <span className="font-semibold">Pressing Étoile</span>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            <NavLink
              to="/portal/orders"
              className={({ isActive }) =>
                cn("rounded-md px-3 py-1.5 font-medium", isActive ? "bg-accent" : "text-muted-foreground hover:text-foreground")
              }
            >
              Mes commandes
            </NavLink>
            <span className="mx-1 hidden text-muted-foreground sm:inline">{customer?.fullName}</span>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Déconnexion">
              <LogOut className="h-4 w-4" />
            </Button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl p-4">
        <Outlet />
      </main>
      <NavLink
        to="/portal/orders/new"
        className="fixed bottom-6 right-6 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90"
        aria-label="Nouvelle commande"
      >
        <Plus className="h-6 w-6" />
      </NavLink>
    </div>
  );
}

import { ReactNode } from "react";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Route-level permission gate. Hiding a page from the sidebar was never a
 * security measure by itself — a CASHIER could still type /reports in the
 * address bar and land on a page whose API calls then fail one by one with
 * confusing errors. This blocks the page itself with a clear message,
 * matching what the backend already enforces on every one of those calls
 * (requirePermission in middleware/auth.ts) — belt and suspenders, not a
 * replacement for it.
 */
export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { hasPermission } = useAuth();
  if (!hasPermission(permission)) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border py-24 text-center">
        <ShieldAlert className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Accès refusé</p>
          <p className="text-sm text-muted-foreground">Votre rôle ne permet pas d'accéder à cette page.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

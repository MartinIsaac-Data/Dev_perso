import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Logo, LogoMark } from "@/components/Logo";
import { landingRouteForRole } from "@/lib/roles";

const DEMO_ACCOUNTS = [
  { role: "SUPER_ADMIN", email: "superadmin@pressing.demo" },
  { role: "MANAGER", email: "manager@pressing.demo" },
  { role: "CASHIER", email: "cashier1@pressing.demo" },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("manager@pressing.demo");
  const [password, setPassword] = useState("Demo1234!");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    const from = (location.state as { from?: string })?.from || landingRouteForRole(user.role);
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const loggedInUser = await login(email, password);
      navigate(landingRouteForRole(loggedInUser.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de connexion");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        <svg
          className="pointer-events-none absolute -bottom-24 -right-24 h-96 w-96 opacity-[0.07]"
          viewBox="0 0 200 200"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M20 100c30-40 60-40 90 0s60 40 90 0"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
          />
          <path
            d="M20 140c30-40 60-40 90 0s60 40 90 0"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
          />
        </svg>
        <div className="flex items-center gap-2.5">
          <LogoMark className="h-8 w-8" />
          <span className="font-display text-lg font-medium tracking-tight">
            NMI <span className="font-semibold">Clean</span>
          </span>
        </div>
        <div>
          <p className="font-display text-4xl font-medium leading-tight text-balance">Clean, simplified.</p>
          <p className="mt-4 max-w-sm text-sm text-primary-foreground/70">
            Le client dépose. NMI Clean s'occupe du reste — suivi, notifications et historique, du dépôt à la livraison.
          </p>
        </div>
      </div>

      <div className="flex w-full items-center justify-center bg-muted/40 p-4 lg:w-1/2">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex flex-col items-center gap-2 text-center lg:hidden">
            <Logo size="lg" withWordmark={false} />
            <h1 className="font-display text-xl font-medium">NMI Clean</h1>
            <p className="text-sm text-muted-foreground">Connectez-vous pour gérer votre pressing</p>
          </div>
          <div className="hidden text-center lg:block">
            <h1 className="font-display text-xl font-medium">Connexion</h1>
            <p className="mt-1 text-sm text-muted-foreground">Accédez à votre espace de gestion</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Mot de passe</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Connexion..." : "Se connecter"}
            </Button>
          </form>

          <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
            <p className="mb-1 font-medium">Comptes de démonstration (mot de passe : Demo1234!)</p>
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.email}
                type="button"
                onClick={() => setEmail(a.email)}
                className="block w-full rounded px-1 py-0.5 text-left hover:bg-accent"
              >
                {a.role} — {a.email}
              </button>
            ))}
          </div>

          <div className="space-y-1.5 text-center text-xs text-muted-foreground">
            <p>
              Vous êtes un client ?{" "}
              <Link to="/portal/login" className="hover:underline">
                Réservez en ligne
              </Link>
            </p>
            <p>
              Vous avez une commande en cours ?{" "}
              <Link to="/track" className="hover:underline">
                Suivre ma commande
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { usePortalAuth } from "@/contexts/PortalAuthContext";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Logo, LogoMark } from "@/components/Logo";

export default function PortalLoginPage() {
  const { customer, login } = usePortalAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const resetSuccess = Boolean((location.state as { resetSuccess?: boolean } | null)?.resetSuccess);

  if (customer) {
    const from = (location.state as { from?: string })?.from || "/portal/orders";
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(identifier, password);
      navigate("/portal/orders");
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
          <path d="M20 100c30-40 60-40 90 0s60 40 90 0" stroke="currentColor" strokeWidth="10" strokeLinecap="round" />
          <path d="M20 140c30-40 60-40 90 0s60 40 90 0" stroke="currentColor" strokeWidth="10" strokeLinecap="round" />
        </svg>
        <div className="flex items-center gap-2.5">
          <LogoMark className="h-8 w-8" />
          <span className="font-display text-lg font-medium tracking-tight">
            NMI <span className="font-semibold">Clean</span>
          </span>
        </div>
        <div>
          <p className="font-display text-4xl font-medium leading-tight text-balance">Confiez. Suivez. Récupérez.</p>
          <p className="mt-4 max-w-sm text-sm text-primary-foreground/70">
            Votre compte réunit vos commandes en cours, votre historique et le suivi en direct — sans passer par la boutique.
          </p>
        </div>
      </div>

      <div className="flex w-full items-center justify-center bg-muted/40 p-4 lg:w-1/2">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex flex-col items-center gap-2 text-center lg:hidden">
            <Logo size="lg" withWordmark={false} />
            <h1 className="font-display text-xl font-medium">NMI Clean</h1>
            <p className="text-sm text-muted-foreground">Connectez-vous pour réserver et suivre vos commandes</p>
          </div>
          <div className="hidden text-center lg:block">
            <h1 className="font-display text-xl font-medium">Votre espace client</h1>
            <p className="mt-1 text-sm text-muted-foreground">Connectez-vous pour continuer</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="space-y-1.5">
              <Label htmlFor="identifier">Téléphone ou email</Label>
              <Input
                id="identifier"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Mot de passe</Label>
                <Link to="/portal/forgot-password" className="text-xs text-primary hover:underline">
                  Mot de passe oublié ?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {resetSuccess && <p className="text-sm text-success">Mot de passe mis à jour, connectez-vous.</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Connexion..." : "Se connecter"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Pas encore de compte ?{" "}
            <Link to="/portal/register" className="font-medium text-primary hover:underline">
              Créer un compte
            </Link>
          </p>
          <p className="text-center text-sm">
            <Link to="/track" className="font-medium text-primary hover:underline">
              Suivre ma commande
            </Link>{" "}
            <span className="text-muted-foreground">sans compte</span>
          </p>
          <p className="text-center text-xs text-muted-foreground">
            Vous êtes un employé ?{" "}
            <Link to="/login" className="hover:underline">
              Connexion personnel
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

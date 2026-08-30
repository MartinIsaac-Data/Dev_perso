import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Logo } from "@/components/Logo";

export default function PortalForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"request" | "reset">("request");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleRequestCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.post("/portal-auth/forgot-password", { identifier });
      setInfo(res.data.message);
      setStep("reset");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReset(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.post("/portal-auth/reset-password", { identifier, code, newPassword });
      navigate("/portal/login", { state: { resetSuccess: true } });
    } catch (err) {
      setError(apiErrorMessage(err, "Code invalide ou expiré"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <Logo size="lg" withWordmark={false} />
          <h1 className="font-display text-xl font-medium">Mot de passe oublié</h1>
          <p className="text-sm text-muted-foreground">
            {step === "request"
              ? "Recevez un code par SMS, WhatsApp et/ou email pour réinitialiser votre mot de passe"
              : "Entrez le code reçu et votre nouveau mot de passe"}
          </p>
        </div>

        {step === "request" ? (
          <form onSubmit={handleRequestCode} className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
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
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Envoi..." : "Recevoir le code"}
            </Button>
          </form>
        ) : (
          <form onSubmit={handleReset} className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
            {info && <p className="text-sm text-muted-foreground">{info}</p>}
            <div className="space-y-1.5">
              <Label htmlFor="code">Code reçu (6 chiffres)</Label>
              <Input
                id="code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                maxLength={6}
                required
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newPassword">Nouveau mot de passe</Label>
              <Input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={6}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Validation..." : "Réinitialiser le mot de passe"}
            </Button>
            <button
              type="button"
              onClick={() => setStep("request")}
              className="w-full text-center text-xs text-muted-foreground hover:underline"
            >
              Je n'ai pas reçu de code, recommencer
            </button>
          </form>
        )}

        <p className="text-center text-xs text-muted-foreground">
          <Link to="/portal/login" className="hover:underline">
            Retour à la connexion
          </Link>
        </p>
      </div>
    </div>
  );
}

import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { usePortalAuth } from "@/contexts/PortalAuthContext";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Logo } from "@/components/Logo";

export default function PortalRegisterPage() {
  const { customer, register } = usePortalAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ fullName: "", phone: "", email: "", address: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (customer) return <Navigate to="/portal/orders" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        fullName: form.fullName,
        phone: form.phone,
        email: form.email || undefined,
        address: form.address || undefined,
        password: form.password,
      });
      navigate("/portal/orders");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création du compte");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <Logo size="lg" withWordmark={false} />
          <h1 className="font-display text-xl font-medium">Créer un compte</h1>
          <p className="text-sm text-muted-foreground">Réservez vos passages chez NMI Clean en ligne</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
          <div className="space-y-1.5">
            <Label htmlFor="fullName">Nom complet</Label>
            <Input
              id="fullName"
              value={form.fullName}
              onChange={(e) => setForm({ ...form, fullName: e.target.value })}
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="phone">Téléphone</Label>
            <Input id="phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email (facultatif)</Label>
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="address">Adresse (facultatif)</Label>
            <Input id="address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Mot de passe</Label>
            <Input
              id="password"
              type="password"
              minLength={6}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Création..." : "Créer mon compte"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Déjà un compte ?{" "}
          <Link to="/portal/login" className="font-medium text-primary hover:underline">
            Se connecter
          </Link>
        </p>
      </div>
    </div>
  );
}

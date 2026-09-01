import { FormEvent, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/states";
import { useAuth } from "@/contexts/AuthContext";

interface Settings {
  businessName: string;
  phone: string;
  email: string;
  address: string;
  currency: string;
  taxRate: number;
  openingHours: string;
  termsAndConditions: string;
  paymentsSimulationMode: boolean;
  notificationsSimulationMode: boolean;
}

export default function SettingsPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Settings | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: async () => (await api.get<Settings>("/settings")).data,
  });

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSubmitting(true);
    try {
      await api.put("/settings", form);
      toast.success("Paramètres mis à jour");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading || !form) return <Skeleton className="h-96 w-full" />;

  const readOnly = !hasPermission("settings:write");

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Paramètres</h1>
        <p className="text-sm text-muted-foreground">Informations générales du pressing</p>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>Informations de l'entreprise</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Nom du pressing</Label>
                <Input
                  disabled={readOnly}
                  value={form.businessName}
                  onChange={(e) => setForm({ ...form, businessName: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Devise</Label>
                <Input disabled={readOnly} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Téléphone</Label>
                <Input disabled={readOnly} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Email</Label>
                <Input disabled={readOnly} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>TVA (%)</Label>
                <Input
                  disabled={readOnly}
                  type="number"
                  value={form.taxRate}
                  onChange={(e) => setForm({ ...form, taxRate: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Horaires</Label>
                <Input disabled={readOnly} value={form.openingHours} onChange={(e) => setForm({ ...form, openingHours: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Adresse</Label>
              <Input disabled={readOnly} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Conditions générales</Label>
              <Textarea
                disabled={readOnly}
                rows={3}
                value={form.termsAndConditions}
                onChange={(e) => setForm({ ...form, termsAndConditions: e.target.value })}
              />
            </div>
            {!readOnly && (
              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Mode démonstration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Quand ces options sont activées, les paiements Orange Money / MTN MoMo et les notifications
              SMS/WhatsApp sont simulés (aucun vrai débit, aucun vrai message envoyé) — utile pour une présentation
              en direct sans compte marchand ni crédit SMS réel. Les intégrations réelles sont utilisées dès qu'un
              opérateur ou Twilio/WhatsApp sont configurés côté serveur et que ces options sont désactivées.
            </p>
            <label className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
              <div>
                <p className="text-sm font-medium">Simulation des paiements mobile money</p>
                <p className="text-xs text-muted-foreground">Orange Money et MTN MoMo répondent instantanément avec un succès simulé.</p>
              </div>
              <input
                type="checkbox"
                disabled={readOnly}
                checked={form.paymentsSimulationMode}
                onChange={(e) => setForm({ ...form, paymentsSimulationMode: e.target.checked })}
              />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
              <div>
                <p className="text-sm font-medium">Simulation des notifications SMS/WhatsApp</p>
                <p className="text-xs text-muted-foreground">Les messages sont enregistrés et affichés en console au lieu d'être réellement envoyés.</p>
              </div>
              <input
                type="checkbox"
                disabled={readOnly}
                checked={form.notificationsSimulationMode}
                onChange={(e) => setForm({ ...form, notificationsSimulationMode: e.target.checked })}
              />
            </label>
            {!readOnly && (
              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Enregistrement..." : "Enregistrer"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </form>
    </div>
  );
}

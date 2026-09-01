import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatMoney } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import type { Service } from "@/types";

export default function ServicesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["services"],
    queryFn: async () => (await api.get<Service[]>("/services")).data,
  });

  async function toggleActive(service: Service) {
    try {
      await api.put(`/services/${service.id}`, { active: !service.active });
      queryClient.invalidateQueries({ queryKey: ["services"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Services</h1>
          <p className="text-sm text-muted-foreground">Catalogue et tarification</p>
        </div>
        {hasPermission("services:write") && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Nouveau service
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucun service" description="Ajoutez votre premier service." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead className="hidden md:table-cell">Catégorie</TableHead>
                <TableHead>Prix standard</TableHead>
                <TableHead className="hidden lg:table-cell">Prix express</TableHead>
                <TableHead className="hidden lg:table-cell">Délai</TableHead>
                <TableHead>Statut</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell className="hidden md:table-cell">{s.category}</TableCell>
                  <TableCell>{formatMoney(s.price)}</TableCell>
                  <TableCell className="hidden lg:table-cell">{s.expressPrice ? formatMoney(s.expressPrice) : "—"}</TableCell>
                  <TableCell className="hidden lg:table-cell">{s.standardDurationHours}h</TableCell>
                  <TableCell>
                    <button onClick={() => toggleActive(s)} disabled={!hasPermission("services:write")}>
                      <Badge tone={s.active ? "success" : "muted"}>{s.active ? "Actif" : "Inactif"}</Badge>
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <CreateServiceDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["services"] })}
      />
    </div>
  );
}

function CreateServiceDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/services", {
        name: form.get("name"),
        category: form.get("category"),
        description: form.get("description") || undefined,
        price: Number(form.get("price")),
        expressPrice: form.get("expressPrice") ? Number(form.get("expressPrice")) : undefined,
        standardDurationHours: Number(form.get("standardDurationHours") || 48),
      });
      toast.success("Service créé");
      onCreated();
      onClose();
      e.currentTarget.reset();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Nouveau service">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="name">Nom *</Label>
          <Input id="name" name="name" required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="category">Catégorie *</Label>
          <Input id="category" name="category" required placeholder="Lavage, Nettoyage à sec..." />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="price">Prix standard (FCFA) *</Label>
            <Input id="price" name="price" type="number" min="0" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="expressPrice">Prix express (FCFA)</Label>
            <Input id="expressPrice" name="expressPrice" type="number" min="0" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="standardDurationHours">Délai standard (heures)</Label>
          <Input id="standardDurationHours" name="standardDurationHours" type="number" min="1" defaultValue={48} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="description">Description</Label>
          <Textarea id="description" name="description" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Création..." : "Créer le service"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatMoney } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import type { Role } from "@/types";

interface EmployeeRow {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  position?: string | null;
  active: boolean;
  performance: { ordersHandled: number; revenueGenerated: number; itemsProcessed: number; lateOrders: number };
}

const ROLES: Role[] = ["SUPER_ADMIN", "ADMIN", "MANAGER", "CASHIER", "OPERATOR", "DELIVERY"];

export default function EmployeesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["employees"],
    queryFn: async () => (await api.get<EmployeeRow[]>("/employees")).data,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Employés</h1>
          <p className="text-sm text-muted-foreground">Équipe et performance</p>
        </div>
        {hasPermission("employees:write") && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> Nouvel employé
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucun employé" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead>Rôle</TableHead>
                <TableHead>Poste</TableHead>
                <TableHead>Commandes traitées</TableHead>
                <TableHead>Articles traités</TableHead>
                <TableHead>CA généré</TableHead>
                <TableHead>Retards</TableHead>
                <TableHead>Statut</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium">{e.fullName}</TableCell>
                  <TableCell>
                    <Badge>{e.role}</Badge>
                  </TableCell>
                  <TableCell>{e.position ?? "—"}</TableCell>
                  <TableCell>{e.performance.ordersHandled}</TableCell>
                  <TableCell>{e.performance.itemsProcessed}</TableCell>
                  <TableCell>{formatMoney(e.performance.revenueGenerated)}</TableCell>
                  <TableCell>{e.performance.lateOrders}</TableCell>
                  <TableCell>
                    <Badge tone={e.active ? "success" : "muted"}>{e.active ? "Actif" : "Inactif"}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <CreateEmployeeDialog
        open={open}
        onClose={() => setOpen(false)}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["employees"] })}
      />
    </div>
  );
}

function CreateEmployeeDialog({
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
      await api.post("/employees", {
        fullName: form.get("fullName"),
        email: form.get("email"),
        password: form.get("password"),
        role: form.get("role"),
        position: form.get("position") || undefined,
        phone: form.get("phone") || undefined,
      });
      toast.success("Employé créé");
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
    <Dialog open={open} onClose={onClose} title="Nouvel employé">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="fullName">Nom complet *</Label>
          <Input id="fullName" name="fullName" required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email *</Label>
            <Input id="email" name="email" type="email" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Mot de passe *</Label>
            <Input id="password" name="password" type="password" minLength={6} required />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="role">Rôle *</Label>
            <Select id="role" name="role" required>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="position">Poste</Label>
            <Input id="position" name="position" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Téléphone</Label>
          <Input id="phone" name="phone" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Création..." : "Créer"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

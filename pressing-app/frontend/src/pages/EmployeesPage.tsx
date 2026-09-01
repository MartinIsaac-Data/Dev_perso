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
import type { Branch, Role } from "@/types";

interface EmployeeRow {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  position?: string | null;
  active: boolean;
  branchId: string | null;
  branchIds: string[];
  performance: { ordersHandled: number; revenueGenerated: number; itemsProcessed: number; lateOrders: number };
}

const ROLES: Role[] = ["SUPER_ADMIN", "ADMIN", "MANAGER", "CASHIER", "OPERATOR", "DELIVERY"];

export default function EmployeesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<EmployeeRow | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["employees"],
    queryFn: async () => (await api.get<EmployeeRow[]>("/employees")).data,
  });
  const { data: branches } = useQuery({
    queryKey: ["branches"],
    queryFn: async () => (await api.get<Branch[]>("/branches")).data,
    enabled: hasPermission("employees:write"),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["employees"] });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Employés</h1>
          <p className="text-sm text-muted-foreground">Équipe et performance</p>
        </div>
        {hasPermission("employees:write") && (
          <Button onClick={() => setCreateOpen(true)}>
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
                <TableHead className="hidden md:table-cell">Agences</TableHead>
                <TableHead className="hidden lg:table-cell">Poste</TableHead>
                <TableHead className="hidden lg:table-cell">Commandes traitées</TableHead>
                <TableHead className="hidden lg:table-cell">Articles traités</TableHead>
                <TableHead className="hidden md:table-cell">CA généré</TableHead>
                <TableHead className="hidden lg:table-cell">Retards</TableHead>
                <TableHead>Statut</TableHead>
                {hasPermission("employees:write") && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium">{e.fullName}</TableCell>
                  <TableCell>
                    <Badge>{e.role}</Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {e.branchIds.length > 1 ? (
                      <Badge>{e.branchIds.length} agences</Badge>
                    ) : (
                      branches?.find((b) => b.id === e.branchIds[0])?.name ?? "—"
                    )}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">{e.position ?? "—"}</TableCell>
                  <TableCell className="hidden lg:table-cell">{e.performance.ordersHandled}</TableCell>
                  <TableCell className="hidden lg:table-cell">{e.performance.itemsProcessed}</TableCell>
                  <TableCell className="hidden md:table-cell">{formatMoney(e.performance.revenueGenerated)}</TableCell>
                  <TableCell className="hidden lg:table-cell">{e.performance.lateOrders}</TableCell>
                  <TableCell>
                    <Badge tone={e.active ? "success" : "muted"}>{e.active ? "Actif" : "Inactif"}</Badge>
                  </TableCell>
                  {hasPermission("employees:write") && (
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setEditing(e)}>
                        Modifier
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <EmployeeDialog
        key="create"
        open={createOpen}
        branches={branches}
        onClose={() => setCreateOpen(false)}
        onSaved={invalidate}
      />
      <EmployeeDialog
        key={editing?.id ?? "edit-none"}
        open={Boolean(editing)}
        employee={editing}
        branches={branches}
        onClose={() => setEditing(null)}
        onSaved={invalidate}
      />
    </div>
  );
}

function EmployeeDialog({
  open,
  employee,
  branches,
  onClose,
  onSaved,
}: {
  open: boolean;
  employee?: EmployeeRow | null;
  branches?: Branch[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(employee);
  const [selectedBranches, setSelectedBranches] = useState<string[]>(employee?.branchIds ?? []);

  function toggleBranch(id: string) {
    setSelectedBranches((prev) => (prev.includes(id) ? prev.filter((b) => b !== id) : [...prev, id]));
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      if (isEdit && employee) {
        await api.put(`/employees/${employee.id}`, {
          fullName: form.get("fullName"),
          role: form.get("role"),
          position: form.get("position") || undefined,
          phone: form.get("phone") || undefined,
          active: form.get("active") === "on",
          branchIds: selectedBranches,
          ...(form.get("password") ? { password: form.get("password") } : {}),
        });
        toast.success("Employé mis à jour");
      } else {
        await api.post("/employees", {
          fullName: form.get("fullName"),
          email: form.get("email"),
          password: form.get("password"),
          role: form.get("role"),
          position: form.get("position") || undefined,
          phone: form.get("phone") || undefined,
          branchIds: selectedBranches,
        });
        toast.success("Employé créé");
      }
      onSaved();
      onClose();
      e.currentTarget.reset();
      setSelectedBranches([]);
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Modifier l'employé" : "Nouvel employé"}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="fullName">Nom complet *</Label>
          <Input id="fullName" name="fullName" required defaultValue={employee?.fullName} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email {!isEdit && "*"}</Label>
            <Input id="email" name="email" type="email" required={!isEdit} disabled={isEdit} defaultValue={employee?.email} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Mot de passe {isEdit ? "(laisser vide pour ne pas changer)" : "*"}</Label>
            <Input id="password" name="password" type="password" minLength={6} required={!isEdit} />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="role">Rôle *</Label>
            <Select id="role" name="role" required defaultValue={employee?.role}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="position">Poste</Label>
            <Input id="position" name="position" defaultValue={employee?.position ?? ""} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Téléphone</Label>
          <Input id="phone" name="phone" />
        </div>
        {isEdit && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="active" defaultChecked={employee?.active ?? true} />
            Compte actif
          </label>
        )}
        {branches && branches.length > 0 && (
          <div className="space-y-1.5">
            <Label>Agences assignées</Label>
            <p className="text-xs text-muted-foreground">
              Cocher plusieurs agences permet à cet employé de gérer plusieurs boutiques (sélecteur d'agence en haut de l'écran).
            </p>
            <div className="flex flex-col gap-1.5 rounded-md border border-border p-2">
              {branches.map((b) => (
                <label key={b.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedBranches.includes(b.id)}
                    onChange={() => toggleBranch(b.id)}
                  />
                  {b.name}
                </label>
              ))}
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : isEdit ? "Enregistrer" : "Créer"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

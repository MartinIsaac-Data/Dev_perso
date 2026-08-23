import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { useAuth } from "@/contexts/AuthContext";
import type { Branch } from "@/types";

export default function BranchesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Branch | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["branches"],
    queryFn: async () => (await api.get<Branch[]>("/branches")).data,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["branches"] });
    queryClient.invalidateQueries({ queryKey: ["my-branches"] });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Agences</h1>
          <p className="text-sm text-muted-foreground">Boutiques et succursales</p>
        </div>
        {hasPermission("branches:manage") && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Nouvelle agence
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucune agence" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead>Adresse</TableHead>
                <TableHead>Téléphone</TableHead>
                {hasPermission("branches:manage") && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-medium">{b.name}</TableCell>
                  <TableCell>{b.address ?? "—"}</TableCell>
                  <TableCell>{b.phone ?? "—"}</TableCell>
                  {hasPermission("branches:manage") && (
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setEditing(b)}>
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

      <BranchDialog key="create" open={createOpen} onClose={() => setCreateOpen(false)} onSaved={invalidate} />
      <BranchDialog
        key={editing?.id ?? "edit-none"}
        open={Boolean(editing)}
        branch={editing}
        onClose={() => setEditing(null)}
        onSaved={invalidate}
      />
    </div>
  );
}

function BranchDialog({
  open,
  branch,
  onClose,
  onSaved,
}: {
  open: boolean;
  branch?: Branch | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(branch);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    const payload = {
      name: form.get("name"),
      address: form.get("address") || undefined,
      phone: form.get("phone") || undefined,
    };
    try {
      if (isEdit && branch) {
        await api.put(`/branches/${branch.id}`, payload);
        toast.success("Agence mise à jour");
      } else {
        await api.post("/branches", payload);
        toast.success("Agence créée");
      }
      onSaved();
      onClose();
      e.currentTarget.reset();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Modifier l'agence" : "Nouvelle agence"}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="name">Nom *</Label>
          <Input id="name" name="name" required defaultValue={branch?.name} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="address">Adresse</Label>
          <Input id="address" name="address" defaultValue={branch?.address ?? ""} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Téléphone</Label>
          <Input id="phone" name="phone" defaultValue={branch?.phone ?? ""} />
        </div>
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

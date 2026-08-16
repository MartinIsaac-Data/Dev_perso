import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import type { Customer, Paginated } from "@/types";

const TYPE_LABELS: Record<string, string> = { INDIVIDUAL: "Particulier", COMPANY: "Entreprise", VIP: "VIP" };

export default function CustomersPage() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["customers", search, type],
    queryFn: async () => {
      const res = await api.get<Paginated<Customer>>("/customers", { params: { search, type, pageSize: 50 } });
      return res.data;
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Clients</h1>
          <p className="text-sm text-muted-foreground">{data?.total ?? "..."} clients enregistrés</p>
        </div>
        {hasPermission("customers:write") && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Nouveau client
          </Button>
        )}
      </div>

      <Card className="flex flex-wrap gap-3 p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Rechercher par nom ou téléphone..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-44">
          <option value="">Tous les types</option>
          <option value="INDIVIDUAL">Particulier</option>
          <option value="COMPANY">Entreprise</option>
          <option value="VIP">VIP</option>
        </Select>
      </Card>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.data.length ? (
          <EmptyState title="Aucun client" description="Ajoutez votre premier client pour commencer." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead>Téléphone</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Commandes</TableHead>
                <TableHead>Depuis</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.data.map((c) => (
                <TableRow key={c.id} className="cursor-pointer" onClick={() => navigate(`/customers/${c.id}`)}>
                  <TableCell className="font-medium">{c.fullName}</TableCell>
                  <TableCell>{c.phone}</TableCell>
                  <TableCell>
                    <Badge tone={c.type === "VIP" ? "warning" : "muted"}>{TYPE_LABELS[c.type]}</Badge>
                  </TableCell>
                  <TableCell>{c._count?.orders ?? 0}</TableCell>
                  <TableCell>{new Date(c.createdAt).toLocaleDateString("fr-FR")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <CreateCustomerDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["customers"] })}
      />
    </div>
  );
}

function CreateCustomerDialog({
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
      await api.post("/customers", {
        fullName: form.get("fullName"),
        phone: form.get("phone"),
        email: form.get("email") || undefined,
        address: form.get("address") || undefined,
        type: form.get("type"),
        notes: form.get("notes") || undefined,
      });
      toast.success("Client créé");
      onCreated();
      onClose();
      e.currentTarget.reset();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Impossible de créer le client"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Nouveau client">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="fullName">Nom complet *</Label>
          <Input id="fullName" name="fullName" required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Téléphone *</Label>
          <Input id="phone" name="phone" required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" name="email" type="email" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="type">Type</Label>
            <Select id="type" name="type" defaultValue="INDIVIDUAL">
              <option value="INDIVIDUAL">Particulier</option>
              <option value="COMPANY">Entreprise</option>
              <option value="VIP">VIP</option>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="address">Adresse</Label>
          <Input id="address" name="address" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Création..." : "Créer le client"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

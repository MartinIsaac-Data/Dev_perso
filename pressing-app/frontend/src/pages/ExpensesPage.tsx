import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDate, formatMoney } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";

const CATEGORIES = [
  ["CHEMICALS", "Produits chimiques"],
  ["WATER", "Eau"],
  ["ELECTRICITY", "Électricité"],
  ["TRANSPORT", "Transport"],
  ["MAINTENANCE", "Maintenance"],
  ["SALARIES", "Salaires"],
  ["DELIVERY", "Livraison"],
  ["RENT", "Loyer"],
  ["OTHER", "Autres"],
];

interface Expense {
  id: string;
  date: string;
  amount: string | number;
  category: string;
  description?: string | null;
  paymentMethod: string;
  employee?: { fullName: string } | null;
}

export default function ExpensesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["expenses"],
    queryFn: async () => (await api.get<Expense[]>("/expenses")).data,
  });

  const total = data?.reduce((sum, e) => sum + Number(e.amount), 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Dépenses</h1>
          <p className="text-sm text-muted-foreground">Total : {formatMoney(total)}</p>
        </div>
        {hasPermission("expenses:write") && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> Nouvelle dépense
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucune dépense enregistrée" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Catégorie</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Employé</TableHead>
                <TableHead>Moyen</TableHead>
                <TableHead>Montant</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>{formatDate(e.date)}</TableCell>
                  <TableCell>{CATEGORIES.find(([k]) => k === e.category)?.[1] ?? e.category}</TableCell>
                  <TableCell>{e.description ?? "—"}</TableCell>
                  <TableCell>{e.employee?.fullName ?? "—"}</TableCell>
                  <TableCell>{e.paymentMethod}</TableCell>
                  <TableCell className="font-medium">{formatMoney(e.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <ExpenseDialog
        open={open}
        onClose={() => setOpen(false)}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["expenses"] })}
      />
    </div>
  );
}

function ExpenseDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/expenses", {
        amount: Number(form.get("amount")),
        category: form.get("category"),
        description: form.get("description") || undefined,
        paymentMethod: form.get("paymentMethod"),
      });
      toast.success("Dépense enregistrée");
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
    <Dialog open={open} onClose={onClose} title="Nouvelle dépense">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="amount">Montant (FCFA) *</Label>
            <Input id="amount" name="amount" type="number" min={1} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="category">Catégorie *</Label>
            <Select id="category" name="category" required>
              {CATEGORIES.map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="paymentMethod">Moyen de paiement</Label>
          <Select id="paymentMethod" name="paymentMethod" defaultValue="CASH">
            <option value="CASH">Cash</option>
            <option value="ORANGE_MONEY">Orange Money</option>
            <option value="MTN_MOMO">MTN Mobile Money</option>
            <option value="CARD">Carte</option>
            <option value="BANK_TRANSFER">Virement</option>
            <option value="OTHER">Autre</option>
          </Select>
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
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

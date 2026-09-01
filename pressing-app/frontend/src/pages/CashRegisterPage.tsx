import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Lock, Unlock } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";

interface RegisterTotals {
  openingBalance: number;
  totalCash: number;
  totalOrangeMoney: number;
  totalMtnMomo: number;
  totalCard: number;
  totalExpenses: number;
  theoreticalBalance: number;
}
interface RegisterTransaction {
  id: string;
  type: string;
  amount: string | number;
  method: string;
  description?: string | null;
  createdAt: string;
}
interface CurrentRegister {
  id: string;
  openingBalance: string | number;
  openedAt: string;
  transactions: RegisterTransaction[];
  totals: RegisterTotals;
}

export default function CashRegisterPage() {
  const queryClient = useQueryClient();
  const [openDialog, setOpenDialog] = useState(false);
  const [closeDialog, setCloseDialog] = useState(false);

  const { data: register, isLoading } = useQuery({
    queryKey: ["cash-register-current"],
    queryFn: async () => (await api.get<CurrentRegister | null>("/cash-registers/current")).data,
  });

  async function addTransaction(type: string, amount: number, description: string) {
    if (!register) return;
    try {
      await api.post(`/cash-registers/${register.id}/transactions`, { type, amount, method: "CASH", description });
      toast.success("Opération enregistrée");
      queryClient.invalidateQueries({ queryKey: ["cash-register-current"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  if (isLoading) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Caisse</h1>
          <p className="text-sm text-muted-foreground">Ouverture, encaissements et clôture</p>
        </div>
        {register ? (
          <Button variant="destructive" onClick={() => setCloseDialog(true)}>
            <Lock className="h-4 w-4" /> Fermer la caisse
          </Button>
        ) : (
          <Button onClick={() => setOpenDialog(true)}>
            <Unlock className="h-4 w-4" /> Ouvrir la caisse
          </Button>
        )}
      </div>

      {!register ? (
        <EmptyState title="Aucune caisse ouverte" description="Ouvrez la caisse pour commencer la journée." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Solde initial" value={formatMoney(register.totals.openingBalance)} />
            <Kpi label="Total cash" value={formatMoney(register.totals.totalCash)} />
            <Kpi label="Total Orange Money" value={formatMoney(register.totals.totalOrangeMoney)} />
            <Kpi label="Total MTN MoMo" value={formatMoney(register.totals.totalMtnMomo)} />
            <Kpi label="Total carte" value={formatMoney(register.totals.totalCard)} />
            <Kpi label="Total dépenses" value={formatMoney(register.totals.totalExpenses)} />
            <Kpi label="Solde théorique" value={formatMoney(register.totals.theoreticalBalance)} highlight />
          </div>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Opérations manuelles</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <ManualTransactionForm onSubmit={addTransaction} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Historique des opérations</CardTitle>
            </CardHeader>
            {register.transactions.length === 0 ? (
              <CardContent className="text-sm text-muted-foreground">Aucune opération aujourd'hui.</CardContent>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Heure</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="hidden md:table-cell">Méthode</TableHead>
                    <TableHead className="hidden lg:table-cell">Description</TableHead>
                    <TableHead>Montant</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {register.transactions.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell>{formatDateTime(t.createdAt)}</TableCell>
                      <TableCell>{t.type}</TableCell>
                      <TableCell className="hidden md:table-cell">{t.method}</TableCell>
                      <TableCell className="hidden lg:table-cell">{t.description ?? "—"}</TableCell>
                      <TableCell className="font-medium">{formatMoney(t.amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </>
      )}

      <OpenRegisterDialog
        open={openDialog}
        onClose={() => setOpenDialog(false)}
        onOpened={() => queryClient.invalidateQueries({ queryKey: ["cash-register-current"] })}
      />
      {register && (
        <CloseRegisterDialog
          open={closeDialog}
          onClose={() => setCloseDialog(false)}
          registerId={register.id}
          theoretical={register.totals.theoreticalBalance}
          onClosed={() => queryClient.invalidateQueries({ queryKey: ["cash-register-current"] })}
        />
      )}
    </div>
  );
}

function Kpi({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardContent className={`text-lg font-semibold ${highlight ? "text-primary" : ""}`}>{value}</CardContent>
    </Card>
  );
}

function ManualTransactionForm({
  onSubmit,
}: {
  onSubmit: (type: string, amount: number, description: string) => void;
}) {
  const [type, setType] = useState("DEPOSIT");
  const [amount, setAmount] = useState(0);
  const [description, setDescription] = useState("");

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="space-y-1.5">
        <Label>Type</Label>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-40">
          <option value="DEPOSIT">Dépôt</option>
          <option value="WITHDRAWAL">Retrait</option>
          <option value="ADJUSTMENT">Ajustement</option>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Montant</Label>
        <Input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="w-32" />
      </div>
      <div className="space-y-1.5">
        <Label>Description</Label>
        <Input value={description} onChange={(e) => setDescription(e.target.value)} className="w-56" />
      </div>
      <Button
        onClick={() => {
          onSubmit(type, amount, description);
          setAmount(0);
          setDescription("");
        }}
      >
        Enregistrer
      </Button>
    </div>
  );
}

function OpenRegisterDialog({
  open,
  onClose,
  onOpened,
}: {
  open: boolean;
  onClose: () => void;
  onOpened: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/cash-registers/open", { openingBalance: Number(form.get("openingBalance")) || 0 });
      toast.success("Caisse ouverte");
      onOpened();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Ouvrir la caisse">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="openingBalance">Solde initial (FCFA)</Label>
          <Input id="openingBalance" name="openingBalance" type="number" min={0} defaultValue={0} />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Ouverture..." : "Ouvrir"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function CloseRegisterDialog({
  open,
  onClose,
  registerId,
  theoretical,
  onClosed,
}: {
  open: boolean;
  onClose: () => void;
  registerId: string;
  theoretical: number;
  onClosed: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post(`/cash-registers/${registerId}/close`, {
        closingBalanceActual: Number(form.get("closingBalanceActual")),
      });
      toast.success("Caisse fermée");
      onClosed();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Fermer la caisse">
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="text-sm text-muted-foreground">Solde théorique : {formatMoney(theoretical)}</p>
        <div className="space-y-1.5">
          <Label htmlFor="closingBalanceActual">Solde réel compté (FCFA)</Label>
          <Input id="closingBalanceActual" name="closingBalanceActual" type="number" min={0} defaultValue={theoretical} required />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" variant="destructive" disabled={submitting}>
            {submitting ? "Fermeture..." : "Fermer la caisse"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

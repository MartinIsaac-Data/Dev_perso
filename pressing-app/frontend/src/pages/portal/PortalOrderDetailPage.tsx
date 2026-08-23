import { FormEvent, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Smartphone } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select } from "@/components/ui/input";
import { TableSkeleton } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";
import { ARTICLE_CATEGORY_LABELS, ORDER_STATUS_LABELS, ORDER_STATUS_TONE, PAYMENT_STATUS_LABELS, PAYMENT_STATUS_TONE } from "@/lib/statusMeta";
import { useMobileMoneyIntent } from "@/hooks/useMobileMoneyIntent";
import { MobileMoneyStatus } from "@/components/MobileMoneyStatus";
import type { Order } from "@/types";

export default function PortalOrderDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [payOpen, setPayOpen] = useState(false);

  const { data: order, isLoading } = useQuery({
    queryKey: ["portal-order", id],
    queryFn: async () => (await portalApi.get<Order>(`/portal/orders/${id}`)).data,
  });

  if (isLoading) return <TableSkeleton />;
  if (!order) return null;

  const balance = Number(order.balance);

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-4 w-4" /> Retour
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{order.orderNumber}</h1>
          <p className="text-sm text-muted-foreground">Déposée le {formatDateTime(order.depositDate)}</p>
        </div>
        {balance > 0 && (
          <Button onClick={() => setPayOpen(true)}>
            <Smartphone className="h-4 w-4" /> Payer maintenant
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Statut</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge tone={ORDER_STATUS_TONE[order.status]}>{ORDER_STATUS_LABELS[order.status]}</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Total</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{formatMoney(order.total)}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Solde</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">
            {formatMoney(order.balance)}{" "}
            <Badge tone={PAYMENT_STATUS_TONE[order.paymentStatus]} className="ml-1">
              {PAYMENT_STATUS_LABELS[order.paymentStatus]}
            </Badge>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Suivi</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {order.statusHistory?.map((h) => (
              <li key={h.id} className="flex items-start gap-3 text-sm">
                <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" />
                <div>
                  <p className="font-medium">{ORDER_STATUS_LABELS[h.status]}</p>
                  <p className="text-muted-foreground">{formatDateTime(h.createdAt)}</p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Articles</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Catégorie</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Qté</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {order.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{ARTICLE_CATEGORY_LABELS[item.category] ?? item.category}</TableCell>
                <TableCell>{item.articleType}</TableCell>
                <TableCell>{item.quantity}</TableCell>
                <TableCell className="font-medium">{formatMoney(item.totalPrice)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        Payez en ligne par Orange Money ou MTN Mobile Money, ou réglez au retrait / à la livraison en boutique.
      </p>

      <PortalPaymentDialog
        open={payOpen}
        orderId={order.id}
        balance={balance}
        onClose={() => setPayOpen(false)}
        onPaid={() => queryClient.invalidateQueries({ queryKey: ["portal-order", id] })}
      />
    </div>
  );
}

function PortalPaymentDialog({
  open,
  orderId,
  balance,
  onClose,
  onPaid,
}: {
  open: boolean;
  orderId: string;
  balance: number;
  onClose: () => void;
  onPaid: () => void;
}) {
  const [provider, setProvider] = useState("ORANGE_MONEY");
  const { intent, initiate, reset } = useMobileMoneyIntent(() => {
    onPaid();
  }, portalApi);

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    await initiate(`/portal/orders/${orderId}/mobile-money`, "/portal/payment-intents", {
      provider,
      phone: form.get("phone"),
      amount: Number(form.get("amount")),
    });
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Payer en ligne">
      {intent ? (
        <MobileMoneyStatus intent={intent} onClose={handleClose} />
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <p className="text-sm text-muted-foreground">Solde restant : {formatMoney(balance)}</p>
          <div className="space-y-1.5">
            <Label htmlFor="amount">Montant *</Label>
            <Input id="amount" name="amount" type="number" min={1} max={balance} defaultValue={balance} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="provider">Opérateur</Label>
            <Select id="provider" name="provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="ORANGE_MONEY">Orange Money</option>
              <option value="MTN_MOMO">MTN Mobile Money</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="phone">Numéro {provider === "ORANGE_MONEY" ? "Orange Money" : "MTN MoMo"} *</Label>
            <Input id="phone" name="phone" placeholder="+237 6XX XXX XXX" required />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Annuler
            </Button>
            <Button type="submit">Envoyer la demande</Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

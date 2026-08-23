import { FormEvent, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Printer, Share2, CreditCard } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select } from "@/components/ui/input";
import { TableSkeleton } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";
import {
  ARTICLE_CATEGORY_LABELS,
  ORDER_STATUS_FLOW,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONE,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_TONE,
} from "@/lib/statusMeta";
import { useAuth } from "@/contexts/AuthContext";
import { useMobileMoneyIntent } from "@/hooks/useMobileMoneyIntent";
import { MobileMoneyStatus } from "@/components/MobileMoneyStatus";
import type { Order } from "@/types";

export default function OrderDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hasPermission } = useAuth();
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [ticketOpen, setTicketOpen] = useState(false);

  const { data: order, isLoading } = useQuery({
    queryKey: ["order", id],
    queryFn: async () => (await api.get<Order>(`/orders/${id}`)).data,
  });

  async function advanceStatus(status: string) {
    try {
      await api.post(`/orders/${id}/status`, { status });
      toast.success("Statut mis à jour");
      queryClient.invalidateQueries({ queryKey: ["order", id] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  if (isLoading) return <TableSkeleton />;
  if (!order) return null;

  const currentIndex = ORDER_STATUS_FLOW.indexOf(order.status);
  const nextStatus = currentIndex >= 0 && currentIndex < ORDER_STATUS_FLOW.length - 1 ? ORDER_STATUS_FLOW[currentIndex + 1] : null;

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-4 w-4" /> Retour
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{order.orderNumber}</h1>
          <p className="text-sm text-muted-foreground">
            <Link to={`/customers/${order.customerId}`} className="hover:underline">
              {order.customer?.fullName}
            </Link>{" "}
            • {order.customer?.phone}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setTicketOpen(true)}>
            <Printer className="h-4 w-4" /> Ticket
          </Button>
          {hasPermission("payments:write") && Number(order.balance) > 0 && (
            <Button onClick={() => setPaymentOpen(true)}>
              <CreditCard className="h-4 w-4" /> Encaisser
            </Button>
          )}
        </div>
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
            <CardTitle>Payé</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{formatMoney(order.paidAmount)}</CardContent>
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

      {hasPermission("orders:status") && order.status !== "COMPLETED" && order.status !== "CANCELLED" && (
        <Card>
          <CardHeader>
            <CardTitle>Faire avancer la commande</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {nextStatus && (
              <Button onClick={() => advanceStatus(nextStatus)}>Passer à « {ORDER_STATUS_LABELS[nextStatus]} »</Button>
            )}
            <Button variant="destructive" onClick={() => advanceStatus("CANCELLED")}>
              Annuler la commande
            </Button>
          </CardContent>
        </Card>
      )}

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
              <TableHead>Service</TableHead>
              <TableHead>Prix unitaire</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {order.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{ARTICLE_CATEGORY_LABELS[item.category] ?? item.category}</TableCell>
                <TableCell>{item.articleType}</TableCell>
                <TableCell>{item.quantity}</TableCell>
                <TableCell>{item.service?.name}</TableCell>
                <TableCell>{formatMoney(item.unitPrice)}</TableCell>
                <TableCell className="font-medium">{formatMoney(item.totalPrice)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Paiements</CardTitle>
        </CardHeader>
        {order.payments && order.payments.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Montant</TableHead>
                <TableHead>Moyen</TableHead>
                <TableHead>Référence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {order.payments.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{formatDateTime(p.paidAt)}</TableCell>
                  <TableCell className="font-medium">{formatMoney(p.amount)}</TableCell>
                  <TableCell>{p.method}</TableCell>
                  <TableCell>{p.reference ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <CardContent className="text-sm text-muted-foreground">Aucun paiement enregistré.</CardContent>
        )}
      </Card>

      <PaymentDialog
        open={paymentOpen}
        onClose={() => setPaymentOpen(false)}
        orderId={order.id}
        balance={Number(order.balance)}
        onPaid={() => queryClient.invalidateQueries({ queryKey: ["order", id] })}
      />
      <TicketDialog open={ticketOpen} onClose={() => setTicketOpen(false)} orderId={order.id} />
    </div>
  );
}

function PaymentDialog({
  open,
  onClose,
  orderId,
  balance,
  onPaid,
}: {
  open: boolean;
  onClose: () => void;
  orderId: string;
  balance: number;
  onPaid: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [method, setMethod] = useState("CASH");
  const isMobileMoney = method === "ORANGE_MONEY" || method === "MTN_MOMO";
  const { intent, initiate, reset } = useMobileMoneyIntent(() => {
    onPaid();
    onClose();
  });

  function handleClose() {
    reset();
    setMethod("CASH");
    onClose();
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const amount = Number(form.get("amount"));

    if (isMobileMoney) {
      await initiate(`/orders/${orderId}/mobile-money`, "/payment-intents", {
        provider: method,
        phone: form.get("phone"),
        amount,
      });
      return;
    }

    setSubmitting(true);
    try {
      await api.post(`/orders/${orderId}/payments`, {
        amount,
        method,
        reference: form.get("reference") || undefined,
      });
      toast.success("Paiement enregistré");
      onPaid();
      handleClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Encaisser un paiement">
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
            <Label htmlFor="method">Moyen de paiement</Label>
            <Select id="method" name="method" value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="CASH">Cash</option>
              <option value="ORANGE_MONEY">Orange Money</option>
              <option value="MTN_MOMO">MTN Mobile Money</option>
              <option value="CARD">Carte</option>
              <option value="BANK_TRANSFER">Virement</option>
              <option value="OTHER">Autre</option>
            </Select>
          </div>
          {isMobileMoney ? (
            <div className="space-y-1.5">
              <Label htmlFor="phone">Numéro {method === "ORANGE_MONEY" ? "Orange Money" : "MTN MoMo"} *</Label>
              <Input id="phone" name="phone" placeholder="+237 6XX XXX XXX" required />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="reference">Référence</Label>
              <Input id="reference" name="reference" />
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Annuler
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Enregistrement..." : isMobileMoney ? "Envoyer la demande" : "Encaisser"}
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

function TicketDialog({ open, onClose, orderId }: { open: boolean; onClose: () => void; orderId: string }) {
  const { data } = useQuery({
    queryKey: ["ticket", orderId],
    queryFn: async () => (await api.get(`/orders/${orderId}/ticket`)).data,
    enabled: open,
  });

  async function handleShare() {
    if (!data) return;
    if (navigator.share) {
      await navigator.share({ title: `Commande ${data.order.orderNumber}`, url: data.trackingUrl });
    } else {
      await navigator.clipboard.writeText(data.trackingUrl);
      toast.success("Lien de suivi copié");
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Ticket de commande">
      {!data ? (
        <p className="text-sm text-muted-foreground">Chargement...</p>
      ) : (
        <div>
          <div id="ticket-print" className="space-y-2 rounded-md border border-border p-4 text-sm">
            <div className="text-center">
              <p className="font-semibold">{data.business.name}</p>
              {data.business.address && <p className="text-xs text-muted-foreground">{data.business.address}</p>}
              {data.business.phone && <p className="text-xs text-muted-foreground">{data.business.phone}</p>}
            </div>
            <hr className="border-border" />
            <p>
              <strong>N° commande :</strong> {data.order.orderNumber}
            </p>
            <p>
              <strong>Client :</strong> {data.order.customer.fullName}
            </p>
            <p>
              <strong>Date :</strong> {formatDateTime(data.order.depositDate)}
            </p>
            <table className="w-full text-xs">
              <tbody>
                {data.order.items.map((item: { id: string; articleType: string; quantity: number; totalPrice: string }) => (
                  <tr key={item.id}>
                    <td>
                      {item.articleType} x{item.quantity}
                    </td>
                    <td className="text-right">{formatMoney(item.totalPrice)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <hr className="border-border" />
            <p className="flex justify-between">
              <span>Total</span> <strong>{formatMoney(data.order.total)}</strong>
            </p>
            <p className="flex justify-between">
              <span>Payé</span> <span>{formatMoney(data.order.paidAmount)}</span>
            </p>
            <p className="flex justify-between">
              <span>Solde</span> <span>{formatMoney(data.order.balance)}</span>
            </p>
            <div className="flex justify-center pt-2">
              <img src={data.qrCodeDataUrl} alt="QR code de suivi" className="h-28 w-28" />
            </div>
            <p className="text-center text-[10px] text-muted-foreground">
              Scannez pour suivre votre commande — {data.trackingUrl}
            </p>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={handleShare}>
              <Share2 className="h-4 w-4" /> Partager
            </Button>
            <Button onClick={() => window.print()}>
              <Printer className="h-4 w-4" /> Imprimer / PDF
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { TableSkeleton } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";
import { ARTICLE_CATEGORY_LABELS, ORDER_STATUS_LABELS, ORDER_STATUS_TONE, PAYMENT_STATUS_LABELS, PAYMENT_STATUS_TONE } from "@/lib/statusMeta";
import type { Order } from "@/types";

export default function PortalOrderDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data: order, isLoading } = useQuery({
    queryKey: ["portal-order", id],
    queryFn: async () => (await portalApi.get<Order>(`/portal/orders/${id}`)).data,
  });

  if (isLoading) return <TableSkeleton />;
  if (!order) return null;

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-4 w-4" /> Retour
      </Button>

      <div>
        <h1 className="text-2xl font-semibold">{order.orderNumber}</h1>
        <p className="text-sm text-muted-foreground">Déposée le {formatDateTime(order.depositDate)}</p>
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
        Le paiement se fait au retrait ou à la livraison, en boutique.
      </p>
    </div>
  );
}

import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDate, formatMoney } from "@/lib/format";
import { ORDER_STATUS_LABELS, ORDER_STATUS_TONE } from "@/lib/statusMeta";
import type { Customer, Order, Payment } from "@/types";

interface CustomerDetail extends Customer {
  orders: Order[];
  payments: Payment[];
  stats: { orderCount: number; totalSpent: number };
}

export default function CustomerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["customer", id],
    queryFn: async () => {
      const res = await api.get<CustomerDetail>(`/customers/${id}`);
      return res.data;
    },
  });

  if (isLoading) return <TableSkeleton />;
  if (!data) return <EmptyState title="Client introuvable" />;

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-4 w-4" /> Retour
      </Button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{data.fullName}</h1>
          <p className="text-sm text-muted-foreground">
            {data.phone} {data.email && `• ${data.email}`}
          </p>
        </div>
        <Link to={`/orders/new?customerId=${data.id}`}>
          <Button>Nouvelle commande</Button>
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Commandes</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{data.stats.orderCount}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Total dépensé</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">{formatMoney(data.stats.totalSpent)}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Type</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge>{data.type}</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Client depuis</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">{formatDate(data.createdAt)}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Historique des commandes</CardTitle>
        </CardHeader>
        {data.orders.length === 0 ? (
          <CardContent>
            <EmptyState title="Aucune commande" />
          </CardContent>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>N° commande</TableHead>
                <TableHead className="hidden sm:table-cell">Date</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead>Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.orders.map((o) => (
                <TableRow key={o.id} className="cursor-pointer" onClick={() => navigate(`/orders/${o.id}`)}>
                  <TableCell className="font-medium">{o.orderNumber}</TableCell>
                  <TableCell className="hidden sm:table-cell">{formatDate(o.depositDate)}</TableCell>
                  <TableCell>
                    <Badge tone={ORDER_STATUS_TONE[o.status]}>{ORDER_STATUS_LABELS[o.status]}</Badge>
                  </TableCell>
                  <TableCell>{formatMoney(o.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

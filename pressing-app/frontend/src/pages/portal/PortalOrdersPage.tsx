import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDate, formatMoney } from "@/lib/format";
import {
  ORDER_SOURCE_LABELS,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONE,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_TONE,
} from "@/lib/statusMeta";
import type { Order } from "@/types";

export default function PortalOrdersPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["portal-orders"],
    queryFn: async () => (await portalApi.get<Order[]>("/portal/orders")).data,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mes commandes</h1>
          <p className="text-sm text-muted-foreground">{data?.length ?? "..."} commande(s)</p>
        </div>
        <Link to="/portal/orders/new">
          <Button>
            <Plus className="h-4 w-4" /> Nouvelle réservation
          </Button>
        </Link>
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucune commande" description="Passez votre première réservation en ligne." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>N° commande</TableHead>
                <TableHead className="hidden lg:table-cell">Origine</TableHead>
                <TableHead className="hidden sm:table-cell">Date</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="hidden md:table-cell">Paiement</TableHead>
                <TableHead>Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="font-medium">
                    <Link to={`/portal/orders/${o.id}`} className="hover:underline">
                      {o.orderNumber}
                    </Link>
                  </TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                    {ORDER_SOURCE_LABELS[o.source]}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{formatDate(o.depositDate)}</TableCell>
                  <TableCell>
                    <Badge tone={ORDER_STATUS_TONE[o.status]}>{ORDER_STATUS_LABELS[o.status]}</Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <Badge tone={PAYMENT_STATUS_TONE[o.paymentStatus]}>{PAYMENT_STATUS_LABELS[o.paymentStatus]}</Badge>
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

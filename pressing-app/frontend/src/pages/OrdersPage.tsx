import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
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
import { useAuth } from "@/contexts/AuthContext";
import type { Order, Paginated } from "@/types";

export default function OrdersPage() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["orders", search, status],
    queryFn: async () => {
      const res = await api.get<Paginated<Order>>("/orders", { params: { search, status, pageSize: 50 } });
      return res.data;
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Commandes</h1>
          <p className="text-sm text-muted-foreground">{data?.total ?? "..."} commandes</p>
        </div>
        {hasPermission("orders:write") && (
          <Link to="/orders/new">
            <Button>
              <Plus className="h-4 w-4" /> Nouvelle commande
            </Button>
          </Link>
        )}
      </div>

      <Card className="flex flex-wrap gap-3 p-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="N° commande, client, téléphone..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-52">
          <option value="">Tous les statuts</option>
          {Object.entries(ORDER_STATUS_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
      </Card>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.data.length ? (
          <EmptyState title="Aucune commande" description="Créez votre première commande." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>N° commande</TableHead>
                <TableHead>Client</TableHead>
                <TableHead className="hidden lg:table-cell">Origine</TableHead>
                <TableHead className="hidden lg:table-cell">Articles</TableHead>
                <TableHead className="hidden sm:table-cell">Date</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="hidden md:table-cell">Paiement</TableHead>
                <TableHead>Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.data.map((o) => (
                <TableRow key={o.id} className="cursor-pointer" onClick={() => navigate(`/orders/${o.id}`)}>
                  <TableCell className="font-medium">{o.orderNumber}</TableCell>
                  <TableCell>{o.customer?.fullName}</TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                    {ORDER_SOURCE_LABELS[o.source]}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">{o.items?.length ?? 0}</TableCell>
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

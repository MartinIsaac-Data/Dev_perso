import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDate, formatMoney } from "@/lib/format";
import { DELIVERY_STATUS_LABELS } from "@/lib/statusMeta";
import { useAuth } from "@/contexts/AuthContext";
import type { Delivery, DeliveryStatusValue } from "@/types";

const STATUS_TONE: Record<DeliveryStatusValue, "muted" | "default" | "success" | "destructive" | "warning"> = {
  PENDING: "muted",
  ASSIGNED: "default",
  PICKED_UP: "default",
  IN_TRANSIT: "warning",
  DELIVERED: "success",
  FAILED: "destructive",
};

export default function DeliveriesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [todayOnly, setTodayOnly] = useState(true);

  const { data, isLoading } = useQuery({
    queryKey: ["deliveries", todayOnly],
    queryFn: async () => (await api.get<Delivery[]>("/deliveries", { params: todayOnly ? { today: "true" } : {} })).data,
  });

  async function updateStatus(id: string, status: DeliveryStatusValue) {
    try {
      await api.put(`/deliveries/${id}`, { status });
      toast.success("Livraison mise à jour");
      queryClient.invalidateQueries({ queryKey: ["deliveries"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Livraisons</h1>
          <p className="text-sm text-muted-foreground">Suivi des livraisons et retraits</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={todayOnly} onChange={(e) => setTodayOnly(e.target.checked)} className="h-4 w-4" />
          Aujourd'hui uniquement
        </label>
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucune livraison" description="Rien à livrer pour le moment." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Commande</TableHead>
                <TableHead>Client</TableHead>
                <TableHead className="hidden lg:table-cell">Adresse</TableHead>
                <TableHead className="hidden md:table-cell">Livreur</TableHead>
                <TableHead className="hidden lg:table-cell">Frais</TableHead>
                <TableHead className="hidden sm:table-cell">Date prévue</TableHead>
                <TableHead>Statut</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="font-medium">{d.order?.orderNumber}</TableCell>
                  <TableCell>{d.order?.customer?.fullName}</TableCell>
                  <TableCell className="hidden lg:table-cell">
                    {[d.address, d.neighborhood, d.city].filter(Boolean).join(", ") || "—"}
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{d.deliverer?.fullName ?? "Non assigné"}</TableCell>
                  <TableCell className="hidden lg:table-cell">{formatMoney(d.fee)}</TableCell>
                  <TableCell className="hidden sm:table-cell">{formatDate(d.scheduledDate)}</TableCell>
                  <TableCell>
                    {hasPermission("deliveries:write") ? (
                      <Select
                        value={d.status}
                        onChange={(e) => updateStatus(d.id, e.target.value as DeliveryStatusValue)}
                        className="w-40"
                      >
                        {Object.entries(DELIVERY_STATUS_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Badge tone={STATUS_TONE[d.status]}>{DELIVERY_STATUS_LABELS[d.status]}</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

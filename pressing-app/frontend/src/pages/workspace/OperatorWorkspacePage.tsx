import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDateTime } from "@/lib/format";
import { ORDER_STATUS_FLOW, ORDER_STATUS_LABELS } from "@/lib/statusMeta";
import { useAuth } from "@/contexts/AuthContext";
import type { Order, OrderStatus, Paginated } from "@/types";

// The stages an operator actually works through — RECEIVED is "not started
// yet" and everything from OUT_FOR_DELIVERY on is out of the workshop's
// hands, so neither gets its own column here.
const WORKSHOP_STAGES: OrderStatus[] = ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY"];

export default function OperatorWorkspacePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["operator-workspace-orders"],
    queryFn: async () =>
      (
        await api.get<Paginated<Order>>("/orders", {
          params: { pageSize: 100 },
        })
      ).data,
  });

  const byStage = useMemo(() => {
    const map = new Map<OrderStatus, Order[]>(WORKSHOP_STAGES.map((s) => [s, []]));
    for (const order of data?.data ?? []) {
      map.get(order.status)?.push(order);
    }
    return map;
  }, [data]);

  async function advance(order: Order) {
    const currentIndex = ORDER_STATUS_FLOW.indexOf(order.status);
    const next = ORDER_STATUS_FLOW[currentIndex + 1];
    if (!next) return;
    try {
      await api.post(`/orders/${order.id}/status`, { status: next });
      toast.success(`${order.orderNumber} → ${ORDER_STATUS_LABELS[next]}`);
      queryClient.invalidateQueries({ queryKey: ["operator-workspace-orders"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Bonjour, {user?.fullName?.split(" ")[0]}</h1>
        <p className="text-sm text-muted-foreground">Espace atelier — que dois-je traiter maintenant ?</p>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {WORKSHOP_STAGES.map((stage) => {
            const orders = byStage.get(stage) ?? [];
            const nextIndex = ORDER_STATUS_FLOW.indexOf(stage) + 1;
            const nextLabel = nextIndex < ORDER_STATUS_FLOW.length ? ORDER_STATUS_LABELS[ORDER_STATUS_FLOW[nextIndex]] : null;
            return (
              <Card key={stage} className="flex flex-col">
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-foreground">{ORDER_STATUS_LABELS[stage]}</CardTitle>
                  <Badge tone="muted">{orders.length}</Badge>
                </CardHeader>
                <CardContent className="flex-1 space-y-2">
                  {orders.length === 0 ? (
                    <p className="py-6 text-center text-xs text-muted-foreground">Rien ici</p>
                  ) : (
                    orders.map((o) => (
                      <div key={o.id} className="rounded-md border border-border p-2.5 text-sm">
                        <button
                          className="block w-full text-left font-medium hover:underline"
                          onClick={() => navigate(`/orders/${o.id}`)}
                        >
                          {o.orderNumber}
                        </button>
                        <p className="text-xs text-muted-foreground">
                          {o.customer?.fullName} • {o.items?.length ?? 0} article(s)
                        </p>
                        <p className="text-xs text-muted-foreground">Déposée {formatDateTime(o.depositDate)}</p>
                        {o.priority === "EXPRESS" && (
                          <Badge tone="warning" className="mt-1">
                            Express
                          </Badge>
                        )}
                        {nextLabel && (
                          <Button size="sm" variant="outline" className="mt-2 w-full" onClick={() => advance(o)}>
                            → {nextLabel}
                          </Button>
                        )}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {!isLoading && [...byStage.values()].every((list) => list.length === 0) && (
        <EmptyState title="Rien à traiter pour le moment" description="Les commandes en cours apparaîtront ici." />
      )}
    </div>
  );
}

import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { MapPin, Phone } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatMoney } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import type { Delivery, DeliveryStatusValue } from "@/types";

const NEXT_ACTION: Partial<Record<DeliveryStatusValue, { label: string; next: DeliveryStatusValue }>> = {
  PENDING: { label: "Marquer récupérée", next: "PICKED_UP" },
  ASSIGNED: { label: "Marquer récupérée", next: "PICKED_UP" },
  PICKED_UP: { label: "Démarrer la livraison", next: "IN_TRANSIT" },
  IN_TRANSIT: { label: "Confirmer la livraison", next: "DELIVERED" },
};

export default function DeliveryWorkspacePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["delivery-workspace", user?.id],
    queryFn: async () =>
      (await api.get<Delivery[]>("/deliveries", { params: { today: "true", delivererId: user!.id } })).data,
    enabled: Boolean(user?.id),
  });

  const groups = useMemo(() => {
    const list = data ?? [];
    return {
      toDo: list.filter((d) => d.status === "PENDING" || d.status === "ASSIGNED" || d.status === "PICKED_UP"),
      inProgress: list.filter((d) => d.status === "IN_TRANSIT"),
      done: list.filter((d) => d.status === "DELIVERED" || d.status === "FAILED"),
    };
  }, [data]);

  async function updateStatus(id: string, status: DeliveryStatusValue) {
    try {
      await api.put(`/deliveries/${id}`, { status });
      toast.success("Livraison mise à jour");
      queryClient.invalidateQueries({ queryKey: ["delivery-workspace"] });
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  if (isLoading) return <TableSkeleton />;

  const total = (data ?? []).length;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Bonjour, {user?.fullName?.split(" ")[0]}</h1>
        <p className="text-sm text-muted-foreground">Mes livraisons du jour — {total} au total</p>
      </div>

      {total === 0 ? (
        <EmptyState title="Aucune livraison aujourd'hui" description="Les livraisons qui vous sont assignées apparaîtront ici." />
      ) : (
        <div className="space-y-6">
          <DeliverySection title="À faire" deliveries={groups.toDo} onAction={updateStatus} />
          <DeliverySection title="En route" deliveries={groups.inProgress} onAction={updateStatus} />
          <DeliverySection title="Terminées" deliveries={groups.done} onAction={updateStatus} collapsedIfEmpty />
        </div>
      )}
    </div>
  );
}

function DeliverySection({
  title,
  deliveries,
  onAction,
  collapsedIfEmpty,
}: {
  title: string;
  deliveries: Delivery[];
  onAction: (id: string, status: DeliveryStatusValue) => void;
  collapsedIfEmpty?: boolean;
}) {
  if (deliveries.length === 0 && collapsedIfEmpty) return null;

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">
        {title} ({deliveries.length})
      </h2>
      {deliveries.length === 0 ? (
        <p className="text-sm text-muted-foreground">Rien pour l'instant.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {deliveries.map((d) => {
            const action = NEXT_ACTION[d.status];
            const amountDue = Number(d.order?.balance ?? 0);
            return (
              <Card key={d.id}>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-foreground">{d.order?.orderNumber}</CardTitle>
                  <Badge tone={d.status === "DELIVERED" ? "success" : d.status === "FAILED" ? "destructive" : "default"}>
                    {d.status}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p className="font-medium">{d.order?.customer?.fullName}</p>
                  <p className="flex items-start gap-1.5 text-muted-foreground">
                    <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {[d.address, d.neighborhood, d.city].filter(Boolean).join(", ") || "Adresse non précisée"}
                  </p>
                  {d.phone && (
                    <a href={`tel:${d.phone}`} className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
                      <Phone className="h-3.5 w-3.5" /> {d.phone}
                    </a>
                  )}
                  {amountDue > 0 && (
                    <p className="font-medium text-destructive">À encaisser : {formatMoney(amountDue)}</p>
                  )}
                  {action && (d.status === "PICKED_UP" || d.status === "IN_TRANSIT" || d.status === "PENDING" || d.status === "ASSIGNED") && (
                    <div className="flex gap-2 pt-1">
                      <Button size="sm" className="flex-1" onClick={() => onAction(d.id, action.next)}>
                        {action.label}
                      </Button>
                      {d.status === "IN_TRANSIT" && (
                        <Button size="sm" variant="destructive" onClick={() => onAction(d.id, "FAILED")}>
                          Échec
                        </Button>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

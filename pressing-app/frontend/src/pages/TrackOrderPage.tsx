import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Search, CheckCircle2, Circle } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Logo } from "@/components/Logo";
import { formatDateTime, formatMoney } from "@/lib/format";
import { ORDER_STATUS_FLOW, ORDER_STATUS_LABELS } from "@/lib/statusMeta";

interface TrackedOrder {
  id: string;
  orderNumber: string;
  status: string;
  depositDate: string;
  estimatedReadyDate?: string | null;
  total: string | number;
  paidAmount: string | number;
  balance: string | number;
  customer: { fullName: string };
  statusHistory: { status: string; createdAt: string; note?: string | null }[];
  items: { articleType: string; quantity: number }[];
}

export default function TrackOrderPage() {
  const [query, setQuery] = useState("");
  const [orders, setOrders] = useState<TrackedOrder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setOrders(null);
    try {
      const isPhone = /^[\d+\s]+$/.test(query.trim());
      const res = await api.get<TrackedOrder[]>("/track", {
        params: isPhone ? { phone: query.trim() } : { orderNumber: query.trim() },
      });
      setOrders(res.data);
    } catch (err) {
      setError(apiErrorMessage(err, "Aucune commande trouvée"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-muted/30 p-4">
      <div className="mx-auto max-w-2xl space-y-6 py-10">
        <div className="flex flex-col items-center gap-2 text-center">
          <Logo size="lg" withWordmark={false} />
          <h1 className="font-display text-xl font-medium">Suivre ma commande</h1>
          <p className="text-sm text-muted-foreground">Numéro de commande ou numéro de téléphone</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row">
          <Input
            placeholder="PR-20260101-0001 ou +237 6..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
          />
          <Button type="submit" disabled={loading} className="sm:shrink-0">
            <Search className="h-4 w-4" /> {loading ? "Recherche..." : "Rechercher"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Nouveau client ?{" "}
          <Link to="/portal/register" className="font-medium text-primary hover:underline">
            Réservez en ligne
          </Link>
        </p>

        <p className="text-center text-xs text-muted-foreground">
          <Link to="/login" className="hover:underline">
            Retour à la connexion
          </Link>
        </p>

        {error && <p className="text-center text-sm text-destructive">{error}</p>}

        <div className="space-y-4">
          {orders?.map((order) => {
            const currentIndex = ORDER_STATUS_FLOW.indexOf(order.status as (typeof ORDER_STATUS_FLOW)[number]);
            return (
              <Card key={order.id}>
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold">{order.orderNumber}</p>
                      <p className="text-sm text-muted-foreground">{order.customer.fullName}</p>
                    </div>
                    <p className="text-sm text-muted-foreground">Déposée le {formatDateTime(order.depositDate)}</p>
                  </div>

                  <ol className="flex flex-wrap gap-x-4 gap-y-2">
                    {ORDER_STATUS_FLOW.map((status, i) => (
                      <li key={status} className="flex items-center gap-1.5 text-xs">
                        {i <= currentIndex ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                        ) : (
                          <Circle className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                        <span className={i <= currentIndex ? "font-medium" : "text-muted-foreground"}>
                          {ORDER_STATUS_LABELS[status]}
                        </span>
                      </li>
                    ))}
                  </ol>

                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <p className="text-muted-foreground">Total</p>
                      <p className="font-medium">{formatMoney(order.total)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Payé</p>
                      <p className="font-medium">{formatMoney(order.paidAmount)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Solde</p>
                      <p className="font-medium">{formatMoney(order.balance)}</p>
                    </div>
                  </div>

                  <p className="text-sm text-muted-foreground">
                    {order.items.map((i) => `${i.articleType} x${i.quantity}`).join(", ")}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

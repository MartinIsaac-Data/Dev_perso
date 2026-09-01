import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Search, UserSearch, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";
import { ORDER_STATUS_LABELS, ORDER_STATUS_TONE } from "@/lib/statusMeta";
import { useAuth } from "@/contexts/AuthContext";
import type { Order, Paginated } from "@/types";

function openSearch() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
}

function isToday(dateStr: string): boolean {
  const d = new Date(dateStr);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

interface RegisterTotals {
  totalCash: number;
  totalOrangeMoney: number;
  totalMtnMomo: number;
  totalCard: number;
}

export default function CashierWorkspacePage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: orders, isLoading } = useQuery({
    queryKey: ["cashier-workspace-orders"],
    queryFn: async () => (await api.get<Paginated<Order>>("/orders", { params: { pageSize: 100 } })).data,
  });

  const { data: register } = useQuery({
    queryKey: ["cash-register-current"],
    queryFn: async () => (await api.get<{ totals: RegisterTotals } | null>("/cash-registers/current")).data,
  });

  const stats = useMemo(() => {
    const list = orders?.data ?? [];
    const receivedToday = list.filter((o) => isToday(o.depositDate));
    const awaitingPayment = list.filter((o) => Number(o.balance) > 0 && o.status !== "CANCELLED");
    const ready = list.filter((o) => o.status === "READY");
    return { receivedToday, awaitingPayment, ready, recent: list.slice(0, 8) };
  }, [orders]);

  const collectedToday = register
    ? Number(register.totals.totalCash) +
      Number(register.totals.totalOrangeMoney) +
      Number(register.totals.totalMtnMomo) +
      Number(register.totals.totalCard)
    : 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Bonjour, {user?.fullName?.split(" ")[0]}</h1>
        <p className="text-sm text-muted-foreground">Espace caissier</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Button size="lg" className="min-h-16 text-base" onClick={() => navigate("/orders/new")}>
          <Plus className="h-5 w-5" /> Nouvelle commande
        </Button>
        <Button size="lg" variant="outline" className="min-h-16" onClick={openSearch}>
          <Search className="h-5 w-5" /> Chercher une commande
        </Button>
        <Button size="lg" variant="outline" className="min-h-16" onClick={openSearch}>
          <UserSearch className="h-5 w-5" /> Chercher un client
        </Button>
        <Link to="/cash-register">
          <Button size="lg" variant="outline" className="min-h-16 w-full">
            <Wallet className="h-5 w-5" /> Ouvrir la caisse
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Reçues aujourd'hui</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{stats.receivedToday.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>En attente de paiement</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{stats.awaitingPayment.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Prêtes</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{stats.ready.length}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Encaissé aujourd'hui</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-primary">{formatMoney(collectedToday)}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Commandes récentes</CardTitle>
        </CardHeader>
        {isLoading ? (
          <TableSkeleton />
        ) : !stats.recent.length ? (
          <EmptyState title="Aucune commande" description="Créez la première commande de la journée." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>N° commande</TableHead>
                <TableHead>Client</TableHead>
                <TableHead className="hidden sm:table-cell">Heure</TableHead>
                <TableHead className="hidden md:table-cell">Statut</TableHead>
                <TableHead>Solde</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.recent.map((o) => (
                <TableRow key={o.id} className="cursor-pointer" onClick={() => navigate(`/orders/${o.id}`)}>
                  <TableCell className="font-medium">{o.orderNumber}</TableCell>
                  <TableCell>{o.customer?.fullName}</TableCell>
                  <TableCell className="hidden sm:table-cell">{formatDateTime(o.depositDate)}</TableCell>
                  <TableCell className="hidden md:table-cell">
                    <Badge tone={ORDER_STATUS_TONE[o.status]}>{ORDER_STATUS_LABELS[o.status]}</Badge>
                  </TableCell>
                  <TableCell className={Number(o.balance) > 0 ? "font-medium text-destructive" : "text-muted-foreground"}>
                    {formatMoney(o.balance)}
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

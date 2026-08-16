import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/states";
import { formatMoney } from "@/lib/format";

const TABS = [
  { key: "sales", label: "Ventes" },
  { key: "clients", label: "Clients" },
  { key: "services", label: "Services" },
  { key: "employees", label: "Employés" },
  { key: "finance", label: "Finance" },
  { key: "operations", label: "Opérations" },
];

const PERIODS = [
  { value: "today", label: "Aujourd'hui" },
  { value: "week", label: "Cette semaine" },
  { value: "month", label: "Ce mois" },
  { value: "quarter", label: "Ce trimestre" },
  { value: "year", label: "Cette année" },
];

export default function ReportsPage() {
  const [tab, setTab] = useState("sales");
  const [period, setPeriod] = useState("month");

  const { data, isLoading } = useQuery({
    queryKey: ["report", tab, period],
    queryFn: async () => (await api.get(`/reports/${tab}`, { params: { period } })).data,
  });

  async function exportCsv() {
    const res = await api.get(`/reports/${tab}`, { params: { period, format: "csv" }, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tab}-report.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Rapports</h1>
          <p className="text-sm text-muted-foreground">Analyse détaillée de l'activité</p>
        </div>
        <div className="flex gap-2">
          <Select value={period} onChange={(e) => setPeriod(e.target.value)} className="w-44">
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
          {["sales", "services", "employees"].includes(tab) && (
            <Button variant="outline" onClick={exportCsv}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-t-md px-4 py-2 text-sm font-medium ${
              tab === t.key ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          {tab === "sales" && data && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <StatCard label="Chiffre d'affaires" value={formatMoney(data.revenue)} />
                <StatCard label="Commandes" value={data.orderCount} />
                <StatCard label="Panier moyen" value={formatMoney(data.averageBasket)} />
              </div>
              <Card>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Commande</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Client</TableHead>
                      <TableHead>Statut</TableHead>
                      <TableHead>Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.orders.map((o: { orderNumber: string; date: string; customer: string; status: string; total: number }) => (
                      <TableRow key={o.orderNumber}>
                        <TableCell>{o.orderNumber}</TableCell>
                        <TableCell>{o.date}</TableCell>
                        <TableCell>{o.customer}</TableCell>
                        <TableCell>{o.status}</TableCell>
                        <TableCell>{formatMoney(o.total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>
          )}

          {tab === "clients" && data && (
            <div className="grid grid-cols-3 gap-4">
              <StatCard label="Nouveaux clients" value={data.newClients} />
              <StatCard label="Clients actifs" value={data.activeClients} />
              <StatCard label="Clients VIP" value={data.vipClients} />
            </div>
          )}

          {tab === "services" && Array.isArray(data) && (
            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Service</TableHead>
                    <TableHead>Quantité</TableHead>
                    <TableHead>CA généré</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((s: { name: string; quantity: number; revenue: number }) => (
                    <TableRow key={s.name}>
                      <TableCell>{s.name}</TableCell>
                      <TableCell>{s.quantity}</TableCell>
                      <TableCell>{formatMoney(s.revenue)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {tab === "employees" && Array.isArray(data) && (
            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Employé</TableHead>
                    <TableHead>Commandes</TableHead>
                    <TableHead>CA généré</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((e: { name: string; orders: number; revenue: number }) => (
                    <TableRow key={e.name}>
                      <TableCell>{e.name}</TableCell>
                      <TableCell>{e.orders}</TableCell>
                      <TableCell>{formatMoney(e.revenue)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {tab === "finance" && data && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <StatCard label="Revenus" value={formatMoney(data.revenue)} />
                <StatCard label="Dépenses" value={formatMoney(data.totalExpenses)} />
                <StatCard label="Bénéfice estimé" value={formatMoney(data.estimatedProfit)} />
              </div>
              <Card>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Catégorie</TableHead>
                      <TableHead>Montant</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.expensesByCategory.map((c: { category: string; total: number }) => (
                      <TableRow key={c.category}>
                        <TableCell>{c.category}</TableCell>
                        <TableCell>{formatMoney(c.total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>
          )}

          {tab === "operations" && data && (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label="Commandes totales" value={data.totalOrders} />
              <StatCard label="Annulées" value={data.cancelled} />
              <StatCard label="En retard / en cours" value={data.lateInProgress} />
              <StatCard label="Délai moyen (heures)" value={data.avgProcessingHours.toFixed(1)} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-xl font-semibold">{value}</CardContent>
    </Card>
  );
}

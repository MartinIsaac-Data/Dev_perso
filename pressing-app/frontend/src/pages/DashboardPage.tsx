import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Banknote,
  CalendarClock,
  CheckCircle2,
  Clock,
  PackageCheck,
  ShoppingBag,
  TrendingUp,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/states";
import { formatMoney } from "@/lib/format";
import type { DashboardData } from "@/types";

const PERIODS = [
  { value: "today", label: "Aujourd'hui" },
  { value: "week", label: "Cette semaine" },
  { value: "month", label: "Ce mois" },
  { value: "quarter", label: "Ce trimestre" },
  { value: "year", label: "Cette année" },
];

const CHART_COLORS = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777"];

export default function DashboardPage() {
  const [period, setPeriod] = useState("month");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", period],
    queryFn: async () => {
      const res = await api.get<DashboardData>("/dashboard", { params: { period } });
      return res.data;
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Vue d'ensemble de l'activité du pressing</p>
        </div>
        <Select value={period} onChange={(e) => setPeriod(e.target.value)} className="w-48">
          {PERIODS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </Select>
      </div>

      {isError && <p className="text-sm text-destructive">Impossible de charger le dashboard.</p>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard icon={Banknote} label="CA du jour" value={data ? formatMoney(data.kpis.revenueToday) : undefined} loading={isLoading} />
        <KpiCard icon={TrendingUp} label="CA du mois" value={data ? formatMoney(data.kpis.revenueMonth) : undefined} loading={isLoading} />
        <KpiCard icon={ShoppingBag} label="Commandes aujourd'hui" value={data?.kpis.ordersToday} loading={isLoading} />
        <KpiCard icon={Clock} label="En cours" value={data?.kpis.ordersInProgress} loading={isLoading} />
        <KpiCard icon={PackageCheck} label="Prêtes" value={data?.kpis.ordersReady} loading={isLoading} />
        <KpiCard icon={CalendarClock} label="En retard" value={data?.kpis.ordersLate} loading={isLoading} tone={data && data.kpis.ordersLate > 0 ? "destructive" : undefined} />
        <KpiCard icon={CheckCircle2} label="Livrées" value={data?.kpis.ordersDelivered} loading={isLoading} />
        <KpiCard icon={Users} label="Clients" value={data?.kpis.customerCount} loading={isLoading} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Paiements en attente</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold text-amber-600 dark:text-amber-400">
            {data ? formatMoney(data.kpis.paymentsPending) : <Skeleton className="h-6 w-24" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Dépenses du jour</CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold">
            {data ? formatMoney(data.kpis.expensesToday) : <Skeleton className="h-6 w-24" />}
          </CardContent>
        </Card>
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Bénéfice estimé (mois en cours)</CardTitle>
          </CardHeader>
          <CardContent
            className={`text-xl font-semibold ${data && data.kpis.estimatedProfit < 0 ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"}`}
          >
            {data ? formatMoney(data.kpis.estimatedProfit) : <Skeleton className="h-6 w-24" />}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Chiffre d'affaires (encaissements)</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {isLoading || !data ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.charts.dailyRevenue}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => formatMoney(v)} />
                  <Line type="monotone" dataKey="total" stroke="#2563eb" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Commandes par statut</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {isLoading || !data ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.charts.ordersByStatus} dataKey="count" nameKey="status" outerRadius={90} label>
                    {data.charts.ordersByStatus.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Services les plus vendus</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {isLoading || !data ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.charts.topServices} layout="vertical" margin={{ left: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => formatMoney(v)} />
                  <Bar dataKey="revenue" fill="#2563eb" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Moyens de paiement</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {isLoading || !data ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.charts.paymentMethodBreakdown} dataKey="total" nameKey="method" outerRadius={90} label>
                    {data.charts.paymentMethodBreakdown.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => formatMoney(v)} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Performance des employés</CardTitle>
        </CardHeader>
        <CardContent className="h-64">
          {isLoading || !data ? (
            <Skeleton className="h-full w-full" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.charts.employeePerformance}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number) => formatMoney(v)} />
                <Bar dataKey="revenue" fill="#16a34a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  loading,
  tone,
}: {
  icon: React.ElementType;
  label: string;
  value?: string | number;
  loading?: boolean;
  tone?: "destructive";
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${tone === "destructive" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>
          <Icon className="h-4.5 w-4.5" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-xs text-muted-foreground">{label}</p>
          {loading || value === undefined ? (
            <Skeleton className="mt-1 h-5 w-16" />
          ) : (
            <p className="break-words text-lg font-semibold leading-tight">{value}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

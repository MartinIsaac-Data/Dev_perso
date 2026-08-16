import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { resolveDateRange } from "../utils/dateRanges";
import { branchScope } from "../middleware/auth";

const ACTIVE_STATUSES = ["RECEIVED", "INSPECTION", "PROCESSING", "QUALITY_CHECK"] as const;

export async function getDashboard(req: Request, res: Response) {
  const { period, from, to } = req.query as Record<string, string>;
  const range = resolveDateRange(period, from, to);

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayEnd = new Date();
  todayEnd.setHours(23, 59, 59, 999);
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);

  const scope = branchScope(req.user!);

  const [
    ordersInRange,
    paymentsInRange,
    customersCount,
    ordersTodayCount,
    revenueTodayAgg,
    revenueMonthAgg,
    expensesTodayAgg,
    expensesMonthAgg,
    pendingBalanceAgg,
    ordersInProgress,
    ordersReady,
    ordersDelivered,
    ordersLate,
  ] = await Promise.all([
    prisma.order.findMany({
      where: { ...scope, depositDate: { gte: range.from, lte: range.to } },
      include: { items: { include: { service: true } }, employee: { select: { id: true, fullName: true } } },
    }),
    prisma.payment.findMany({
      where: { paidAt: { gte: range.from, lte: range.to }, order: scope },
    }),
    prisma.customer.count({ where: { active: true, ...scope } }),
    prisma.order.count({ where: { ...scope, depositDate: { gte: todayStart, lte: todayEnd } } }),
    prisma.payment.aggregate({
      where: { paidAt: { gte: todayStart, lte: todayEnd }, order: scope },
      _sum: { amount: true },
    }),
    prisma.payment.aggregate({
      where: { paidAt: { gte: monthStart, lte: todayEnd }, order: scope },
      _sum: { amount: true },
    }),
    prisma.expense.aggregate({
      where: { ...scope, date: { gte: todayStart, lte: todayEnd } },
      _sum: { amount: true },
    }),
    prisma.expense.aggregate({
      where: { ...scope, date: { gte: monthStart, lte: todayEnd } },
      _sum: { amount: true },
    }),
    prisma.order.aggregate({
      where: { ...scope, paymentStatus: { in: ["UNPAID", "PARTIAL"] } },
      _sum: { balance: true },
    }),
    prisma.order.count({ where: { ...scope, status: { in: [...ACTIVE_STATUSES] } } }),
    prisma.order.count({ where: { ...scope, status: "READY" } }),
    prisma.order.count({ where: { ...scope, status: { in: ["DELIVERED", "COMPLETED"] } } }),
    prisma.order.count({
      where: {
        ...scope,
        status: { notIn: ["COMPLETED", "DELIVERED", "CANCELLED"] },
        estimatedReadyDate: { lt: new Date() },
      },
    }),
  ]);

  // --- charts, aggregated in JS over the already-scoped result sets -------
  const dailyRevenueMap = new Map<string, number>();
  for (const p of paymentsInRange) {
    const key = p.paidAt.toISOString().slice(0, 10);
    dailyRevenueMap.set(key, (dailyRevenueMap.get(key) ?? 0) + Number(p.amount));
  }
  const dailyRevenue = [...dailyRevenueMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, total]) => ({ date, total }));

  const ordersByStatusMap = new Map<string, number>();
  for (const o of ordersInRange) {
    ordersByStatusMap.set(o.status, (ordersByStatusMap.get(o.status) ?? 0) + 1);
  }
  const ordersByStatus = [...ordersByStatusMap.entries()].map(([status, count]) => ({ status, count }));

  const topServicesMap = new Map<string, { name: string; count: number; revenue: number }>();
  const topArticlesMap = new Map<string, number>();
  for (const order of ordersInRange) {
    for (const item of order.items) {
      const entry = topServicesMap.get(item.service.name) ?? {
        name: item.service.name,
        count: 0,
        revenue: 0,
      };
      entry.count += item.quantity;
      entry.revenue += Number(item.totalPrice);
      topServicesMap.set(item.service.name, entry);

      topArticlesMap.set(item.category, (topArticlesMap.get(item.category) ?? 0) + item.quantity);
    }
  }
  const topServices = [...topServicesMap.values()].sort((a, b) => b.revenue - a.revenue).slice(0, 8);
  const topArticles = [...topArticlesMap.entries()]
    .map(([category, quantity]) => ({ category, quantity }))
    .sort((a, b) => b.quantity - a.quantity)
    .slice(0, 8);

  const employeeMap = new Map<string, { name: string; orders: number; revenue: number }>();
  for (const order of ordersInRange) {
    if (!order.employee) continue;
    const entry = employeeMap.get(order.employee.id) ?? {
      name: order.employee.fullName,
      orders: 0,
      revenue: 0,
    };
    entry.orders += 1;
    entry.revenue += Number(order.total);
    employeeMap.set(order.employee.id, entry);
  }
  const employeePerformance = [...employeeMap.values()].sort((a, b) => b.revenue - a.revenue);

  const paymentMethodMap = new Map<string, number>();
  for (const p of paymentsInRange) {
    paymentMethodMap.set(p.method, (paymentMethodMap.get(p.method) ?? 0) + Number(p.amount));
  }
  const paymentMethodBreakdown = [...paymentMethodMap.entries()].map(([method, total]) => ({
    method,
    total,
  }));

  res.json({
    range,
    kpis: {
      revenueToday: revenueTodayAgg._sum.amount ?? 0,
      revenueMonth: revenueMonthAgg._sum.amount ?? 0,
      ordersToday: ordersTodayCount,
      ordersInProgress,
      ordersReady,
      ordersLate,
      ordersDelivered,
      customerCount: customersCount,
      paymentsPending: pendingBalanceAgg._sum.balance ?? 0,
      expensesToday: expensesTodayAgg._sum.amount ?? 0,
      estimatedProfit: Number(revenueMonthAgg._sum.amount ?? 0) - Number(expensesMonthAgg._sum.amount ?? 0),
    },
    charts: {
      dailyRevenue,
      ordersByStatus,
      topServices,
      topArticles,
      employeePerformance,
      paymentMethodBreakdown,
    },
  });
}

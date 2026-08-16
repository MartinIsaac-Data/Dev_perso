import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { resolveDateRange } from "../utils/dateRanges";
import { branchScope } from "../middleware/auth";
import { sendCsv } from "../utils/csv";

function range(req: Request) {
  const { period, from, to } = req.query as Record<string, string>;
  return resolveDateRange(period, from, to);
}

export async function salesReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);
  const orders = await prisma.order.findMany({
    where: { ...scope, depositDate: { gte: from, lte: to }, status: { not: "CANCELLED" } },
    include: { customer: { select: { fullName: true } } },
    orderBy: { depositDate: "asc" },
  });

  const revenue = orders.reduce((sum, o) => sum + Number(o.total), 0);
  const averageBasket = orders.length ? revenue / orders.length : 0;

  const rows = orders.map((o) => ({
    orderNumber: o.orderNumber,
    date: o.depositDate.toISOString().slice(0, 10),
    customer: o.customer.fullName,
    total: Number(o.total),
    status: o.status,
  }));

  if ((req.query.format as string) === "csv") return sendCsv(res, "sales-report.csv", rows);
  res.json({ revenue, orderCount: orders.length, averageBasket, orders: rows });
}

export async function clientsReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);

  const [newClients, activeClients, vipClients] = await Promise.all([
    prisma.customer.count({ where: { ...scope, createdAt: { gte: from, lte: to } } }),
    prisma.customer.count({ where: { ...scope, active: true, orders: { some: { depositDate: { gte: from, lte: to } } } } }),
    prisma.customer.count({ where: { ...scope, type: "VIP", active: true } }),
  ]);

  res.json({ newClients, activeClients, vipClients });
}

export async function servicesReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);
  const items = await prisma.orderItem.findMany({
    where: { order: { ...scope, depositDate: { gte: from, lte: to }, status: { not: "CANCELLED" } } },
    include: { service: true },
  });

  const byService = new Map<string, { name: string; quantity: number; revenue: number }>();
  for (const item of items) {
    const entry = byService.get(item.service.id) ?? { name: item.service.name, quantity: 0, revenue: 0 };
    entry.quantity += item.quantity;
    entry.revenue += Number(item.totalPrice);
    byService.set(item.service.id, entry);
  }

  const rows = [...byService.values()].sort((a, b) => b.revenue - a.revenue);
  if ((req.query.format as string) === "csv") return sendCsv(res, "services-report.csv", rows);
  res.json(rows);
}

export async function employeesReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);
  const orders = await prisma.order.findMany({
    where: { ...scope, depositDate: { gte: from, lte: to } },
    include: { employee: { select: { id: true, fullName: true } } },
  });

  const byEmployee = new Map<string, { name: string; orders: number; revenue: number }>();
  for (const o of orders) {
    if (!o.employee) continue;
    const entry = byEmployee.get(o.employee.id) ?? { name: o.employee.fullName, orders: 0, revenue: 0 };
    entry.orders += 1;
    entry.revenue += Number(o.total);
    byEmployee.set(o.employee.id, entry);
  }

  const rows = [...byEmployee.values()].sort((a, b) => b.revenue - a.revenue);
  if ((req.query.format as string) === "csv") return sendCsv(res, "employees-report.csv", rows);
  res.json(rows);
}

export async function financeReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);

  const [revenueAgg, expenses] = await Promise.all([
    prisma.payment.aggregate({ where: { paidAt: { gte: from, lte: to }, order: scope }, _sum: { amount: true } }),
    prisma.expense.findMany({ where: { ...scope, date: { gte: from, lte: to } } }),
  ]);

  const totalExpenses = expenses.reduce((sum, e) => sum + Number(e.amount), 0);
  const byCategory = new Map<string, number>();
  for (const e of expenses) byCategory.set(e.category, (byCategory.get(e.category) ?? 0) + Number(e.amount));

  const revenue = Number(revenueAgg._sum.amount ?? 0);
  res.json({
    revenue,
    totalExpenses,
    estimatedProfit: revenue - totalExpenses,
    expensesByCategory: [...byCategory.entries()].map(([category, total]) => ({ category, total })),
  });
}

export async function operationsReport(req: Request, res: Response) {
  const { from, to } = range(req);
  const scope = branchScope(req.user!);

  const orders = await prisma.order.findMany({
    where: { ...scope, depositDate: { gte: from, lte: to } },
    select: { status: true, depositDate: true, completedDate: true },
  });

  const cancelled = orders.filter((o) => o.status === "CANCELLED").length;
  const late = orders.filter(
    (o) => o.status !== "CANCELLED" && o.status !== "COMPLETED" && o.status !== "DELIVERED"
  ).length;
  const completed = orders.filter((o) => o.completedDate);
  const avgProcessingHours =
    completed.length > 0
      ? completed.reduce(
          (sum, o) => sum + (o.completedDate!.getTime() - o.depositDate.getTime()) / 3_600_000,
          0
        ) / completed.length
      : 0;

  res.json({ totalOrders: orders.length, cancelled, lateInProgress: late, avgProcessingHours });
}

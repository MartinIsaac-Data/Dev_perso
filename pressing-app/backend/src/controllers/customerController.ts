import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { customerCreateSchema, customerUpdateSchema } from "../validators/customerValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";

export async function listCustomers(req: Request, res: Response) {
  const { search, type, page = "1", pageSize = "20" } = req.query as Record<string, string>;
  const take = Math.min(Number(pageSize) || 20, 100);
  const skip = (Math.max(Number(page) || 1, 1) - 1) * take;

  const where = {
    active: true,
    ...branchScope(req.user!),
    ...(type ? { type: type as "INDIVIDUAL" | "COMPANY" | "VIP" } : {}),
    ...(search
      ? {
          OR: [
            { fullName: { contains: search, mode: "insensitive" as const } },
            { phone: { contains: search } },
            { email: { contains: search, mode: "insensitive" as const } },
          ],
        }
      : {}),
  };

  const [customers, total] = await Promise.all([
    prisma.customer.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take,
      skip,
      include: { _count: { select: { orders: true } } },
    }),
    prisma.customer.count({ where }),
  ]);

  res.json({ data: customers, total, page: Number(page) || 1, pageSize: take });
}

export async function getCustomer(req: Request, res: Response) {
  const customer = await prisma.customer.findUnique({
    where: { id: req.params.id },
    include: {
      orders: { orderBy: { createdAt: "desc" }, take: 20 },
      payments: { orderBy: { paidAt: "desc" }, take: 20 },
    },
  });
  if (!customer) throw new ApiError(404, "Customer not found");

  const stats = await prisma.order.aggregate({
    where: { customerId: customer.id },
    _sum: { total: true },
    _count: true,
  });

  res.json({
    ...customer,
    stats: {
      orderCount: stats._count,
      totalSpent: stats._sum.total ?? 0,
    },
  });
}

export async function createCustomer(req: Request, res: Response) {
  const data = customerCreateSchema.parse(req.body);
  const customer = await prisma.customer.create({
    data: { ...data, branchId: data.branchId ?? req.user!.branchId },
  });
  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Customer",
    entityId: customer.id,
    newValue: customer,
  });
  res.status(201).json(customer);
}

export async function updateCustomer(req: Request, res: Response) {
  const data = customerUpdateSchema.parse(req.body);
  const existing = await prisma.customer.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Customer not found");

  const customer = await prisma.customer.update({ where: { id: req.params.id }, data });
  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Customer",
    entityId: customer.id,
    oldValue: existing,
    newValue: customer,
  });
  res.json(customer);
}

export async function deactivateCustomer(req: Request, res: Response) {
  const existing = await prisma.customer.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Customer not found");

  const customer = await prisma.customer.update({
    where: { id: req.params.id },
    data: { active: false },
  });
  await recordAudit({
    userId: req.user!.id,
    action: "DEACTIVATE",
    entityType: "Customer",
    entityId: customer.id,
    oldValue: existing,
    newValue: customer,
  });
  res.json(customer);
}

import { Request, Response } from "express";
import bcrypt from "bcryptjs";
import { prisma } from "../lib/prisma";
import { userCreateSchema, userUpdateSchema } from "../validators/userValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";

const SAFE_SELECT = {
  id: true,
  email: true,
  fullName: true,
  phone: true,
  role: true,
  position: true,
  hireDate: true,
  active: true,
  branchId: true,
  createdAt: true,
} as const;

export async function listEmployees(req: Request, res: Response) {
  const users = await prisma.user.findMany({
    where: { ...branchScope(req.user!) },
    select: SAFE_SELECT,
    orderBy: { fullName: "asc" },
  });

  const stats = await Promise.all(
    users.map(async (user) => {
      const [orderStats, itemCount, lateCount] = await Promise.all([
        prisma.order.aggregate({
          where: { employeeId: user.id },
          _count: true,
          _sum: { total: true },
        }),
        prisma.orderItem.count({ where: { order: { employeeId: user.id } } }),
        prisma.order.count({
          where: {
            employeeId: user.id,
            status: { notIn: ["COMPLETED", "DELIVERED", "CANCELLED"] },
            estimatedReadyDate: { lt: new Date() },
          },
        }),
      ]);
      return {
        ...user,
        performance: {
          ordersHandled: orderStats._count,
          revenueGenerated: orderStats._sum.total ?? 0,
          itemsProcessed: itemCount,
          lateOrders: lateCount,
        },
      };
    })
  );

  res.json(stats);
}

export async function createEmployee(req: Request, res: Response) {
  const data = userCreateSchema.parse(req.body);
  const existing = await prisma.user.findUnique({ where: { email: data.email } });
  if (existing) throw new ApiError(409, "Email already in use");

  const passwordHash = await bcrypt.hash(data.password, 10);
  const user = await prisma.user.create({
    data: {
      email: data.email,
      passwordHash,
      fullName: data.fullName,
      phone: data.phone,
      role: data.role,
      position: data.position,
      hireDate: data.hireDate,
      branchId: data.branchId,
    },
    select: SAFE_SELECT,
  });

  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "User",
    entityId: user.id,
    newValue: user,
  });

  res.status(201).json(user);
}

export async function updateEmployee(req: Request, res: Response) {
  const data = userUpdateSchema.parse(req.body);
  const existing = await prisma.user.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "User not found");

  const passwordHash = data.password ? await bcrypt.hash(data.password, 10) : undefined;

  const user = await prisma.user.update({
    where: { id: req.params.id },
    data: {
      fullName: data.fullName,
      phone: data.phone,
      role: data.role,
      position: data.position,
      active: data.active,
      branchId: data.branchId,
      ...(passwordHash ? { passwordHash } : {}),
    },
    select: SAFE_SELECT,
  });

  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "User",
    entityId: user.id,
    oldValue: { ...existing, passwordHash: undefined },
    newValue: user,
  });

  res.json(user);
}

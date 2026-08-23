import { Request, Response } from "express";
import bcrypt from "bcryptjs";
import { prisma } from "../lib/prisma";
import { userCreateSchema, userUpdateSchema } from "../validators/userValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";
import { branchScope } from "../middleware/auth";
import { getAccessibleBranchIds, setStaffBranches } from "../services/branchService";

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
  branchAssignments: { select: { branchId: true } },
} as const;

function withBranchIds<T extends { branchId: string | null; branchAssignments: { branchId: string }[] }>(
  user: T
) {
  const { branchAssignments, ...rest } = user;
  const ids = new Set(branchAssignments.map((a) => a.branchId));
  if (rest.branchId) ids.add(rest.branchId);
  return { ...rest, branchIds: [...ids] };
}

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
        ...withBranchIds(user),
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

  // Atomic: the User row, its branch assignments, and the audit entry all
  // commit together or not at all. Previously these ran as separate calls
  // after the User was already created — if setStaffBranches or recordAudit
  // threw, the client saw an error even though the employee had, in fact,
  // been created (a real bug: retrying then hit "Email already in use").
  const result = await prisma.$transaction(async (tx) => {
    const user = await tx.user.create({
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

    const assignedBranchIds =
      data.branchIds && data.branchIds.length > 0 ? data.branchIds : data.branchId ? [data.branchId] : [];
    if (assignedBranchIds.length > 0) {
      await setStaffBranches(user.id, assignedBranchIds, tx);
    }
    const branchIds = await getAccessibleBranchIds(user.id, tx);
    const { branchAssignments: _createdAssignments, ...userWithoutAssignments } = user;
    const created = { ...userWithoutAssignments, branchIds };

    await recordAudit(
      {
        userId: req.user!.id,
        action: "CREATE",
        entityType: "User",
        entityId: user.id,
        newValue: created,
      },
      tx
    );

    return created;
  });

  res.status(201).json(result);
}

export async function updateEmployee(req: Request, res: Response) {
  const data = userUpdateSchema.parse(req.body);
  const existing = await prisma.user.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "User not found");

  const passwordHash = data.password ? await bcrypt.hash(data.password, 10) : undefined;

  const result = await prisma.$transaction(async (tx) => {
    const user = await tx.user.update({
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

    if (data.branchIds) {
      await setStaffBranches(user.id, data.branchIds, tx);
    }
    const branchIds = await getAccessibleBranchIds(user.id, tx);
    const { branchAssignments: _updatedAssignments, ...userWithoutAssignments } = user;
    const updated = { ...userWithoutAssignments, branchIds };

    await recordAudit(
      {
        userId: req.user!.id,
        action: "UPDATE",
        entityType: "User",
        entityId: user.id,
        oldValue: { ...existing, passwordHash: undefined },
        newValue: updated,
      },
      tx
    );

    return updated;
  });

  res.json(result);
}

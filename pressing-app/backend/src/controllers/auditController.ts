import { Request, Response } from "express";
import { prisma } from "../lib/prisma";

export async function listAuditLogs(req: Request, res: Response) {
  const { entityType, userId, page = "1", pageSize = "50" } = req.query as Record<string, string>;
  const take = Math.min(Number(pageSize) || 50, 200);
  const skip = (Math.max(Number(page) || 1, 1) - 1) * take;

  const where = {
    ...(entityType ? { entityType } : {}),
    ...(userId ? { userId } : {}),
  };

  const [logs, total] = await Promise.all([
    prisma.auditLog.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take,
      skip,
      include: { user: { select: { fullName: true, email: true } } },
    }),
    prisma.auditLog.count({ where }),
  ]);

  res.json({ data: logs, total, page: Number(page) || 1, pageSize: take });
}

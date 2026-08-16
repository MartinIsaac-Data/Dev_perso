import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { branchCreateSchema, branchUpdateSchema } from "../validators/branchValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";

export async function listBranches(req: Request, res: Response) {
  const where = req.user!.role === "SUPER_ADMIN" ? {} : { id: req.user!.branchId ?? "" };
  const branches = await prisma.branch.findMany({ where, orderBy: { name: "asc" } });
  res.json(branches);
}

export async function createBranch(req: Request, res: Response) {
  const data = branchCreateSchema.parse(req.body);
  const branch = await prisma.branch.create({ data });
  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Branch",
    entityId: branch.id,
    newValue: branch,
  });
  res.status(201).json(branch);
}

export async function updateBranch(req: Request, res: Response) {
  const data = branchUpdateSchema.parse(req.body);
  const existing = await prisma.branch.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Branch not found");

  const branch = await prisma.branch.update({ where: { id: req.params.id }, data });
  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Branch",
    entityId: branch.id,
    oldValue: existing,
    newValue: branch,
  });
  res.json(branch);
}

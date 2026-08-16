import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { serviceCreateSchema, serviceUpdateSchema } from "../validators/serviceValidators";
import { ApiError } from "../middleware/errorHandler";
import { recordAudit } from "../services/auditService";

export async function listServices(req: Request, res: Response) {
  const { activeOnly } = req.query as Record<string, string>;
  const services = await prisma.service.findMany({
    where: activeOnly === "true" ? { active: true } : {},
    orderBy: { name: "asc" },
  });
  res.json(services);
}

export async function createService(req: Request, res: Response) {
  const data = serviceCreateSchema.parse(req.body);
  const service = await prisma.service.create({ data });
  await recordAudit({
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Service",
    entityId: service.id,
    newValue: service,
  });
  res.status(201).json(service);
}

export async function updateService(req: Request, res: Response) {
  const data = serviceUpdateSchema.parse(req.body);
  const existing = await prisma.service.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Service not found");

  const service = await prisma.service.update({ where: { id: req.params.id }, data });
  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Service",
    entityId: service.id,
    oldValue: existing,
    newValue: service,
  });
  res.json(service);
}

export async function deleteService(req: Request, res: Response) {
  const existing = await prisma.service.findUnique({ where: { id: req.params.id } });
  if (!existing) throw new ApiError(404, "Service not found");
  const service = await prisma.service.update({
    where: { id: req.params.id },
    data: { active: false },
  });
  await recordAudit({
    userId: req.user!.id,
    action: "DEACTIVATE",
    entityType: "Service",
    entityId: service.id,
    oldValue: existing,
    newValue: service,
  });
  res.json(service);
}

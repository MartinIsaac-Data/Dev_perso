import { Request, Response } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { recordAudit } from "../services/auditService";

const DEFAULT_SETTINGS: Record<string, unknown> = {
  businessName: "Mon Pressing",
  logoUrl: null,
  phone: "",
  email: "",
  address: "",
  currency: "FCFA",
  taxRate: 0,
  openingHours: "Lun-Sam 8h-19h",
  termsAndConditions: "Les articles non retirés après 60 jours ne sont plus garantis.",
};

export async function getSettings(_req: Request, res: Response) {
  const rows = await prisma.setting.findMany();
  const stored = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  res.json({ ...DEFAULT_SETTINGS, ...stored });
}

const updateSchema = z.record(z.string(), z.unknown());

export async function updateSettings(req: Request, res: Response) {
  const data = updateSchema.parse(req.body);

  await prisma.$transaction(
    Object.entries(data).map(([key, value]) =>
      prisma.setting.upsert({
        where: { key },
        create: { key, value: value as object },
        update: { value: value as object },
      })
    )
  );

  await recordAudit({
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Setting",
    newValue: data,
  });

  const rows = await prisma.setting.findMany();
  const stored = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  res.json({ ...DEFAULT_SETTINGS, ...stored });
}

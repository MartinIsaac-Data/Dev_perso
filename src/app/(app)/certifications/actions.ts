"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { certificationSchema } from "@/lib/validations/certification";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof certificationSchema.safeParse>) {
  if (!parsed.success) return null;
  const { startDate, examDate, completionDate, expirationDate, ...rest } = parsed.data;
  return {
    ...rest,
    startDate: startDate ? new Date(startDate) : null,
    examDate: examDate ? new Date(examDate) : null,
    completionDate: completionDate ? new Date(completionDate) : null,
    expirationDate: expirationDate ? new Date(expirationDate) : null,
  };
}

export async function createCertification(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = certificationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.certification.create({ data: { userId, ...data } });
  revalidatePath("/certifications");
  revalidatePath("/");
  return { ok: true };
}

export async function updateCertification(
  id: string,
  raw: Record<string, string>,
): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = certificationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.certification.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Certification not found" };

  revalidatePath("/certifications");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteCertification(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.certification.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Certification not found" };

  revalidatePath("/certifications");
  revalidatePath("/");
  return { ok: true };
}

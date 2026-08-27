"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { evidenceSchema } from "@/lib/validations/evidence";

type ActionResult = { ok: boolean; error?: string };

async function assertOwnership(userId: string, projectId?: string, certificationId?: string) {
  if (projectId) {
    const project = await prisma.project.findFirst({ where: { id: projectId, userId } });
    if (!project) throw new Error("Project not found");
  }
  if (certificationId) {
    const cert = await prisma.certification.findFirst({ where: { id: certificationId, userId } });
    if (!cert) throw new Error("Certification not found");
  }
}

function toData(parsed: ReturnType<typeof evidenceSchema.safeParse>) {
  if (!parsed.success) return null;
  const { date, ...rest } = parsed.data;
  return { ...rest, date: date ? new Date(date) : null };
}

export async function createEvidence(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = evidenceSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  try {
    await assertOwnership(userId, data.projectId, data.certificationId);
    await prisma.evidence.create({ data: { userId, ...data } });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not save" };
  }

  revalidatePath("/evidence");
  return { ok: true };
}

export async function updateEvidence(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = evidenceSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  try {
    await assertOwnership(userId, data.projectId, data.certificationId);
    const { count } = await prisma.evidence.updateMany({ where: { id, userId }, data });
    if (count === 0) return { ok: false, error: "Evidence not found" };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not save" };
  }

  revalidatePath("/evidence");
  return { ok: true };
}

export async function deleteEvidence(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.evidence.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Evidence not found" };

  revalidatePath("/evidence");
  return { ok: true };
}

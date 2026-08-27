"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { mbaApplicationSchema } from "@/lib/validations/mba-application";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof mbaApplicationSchema.safeParse>) {
  if (!parsed.success) return null;
  const { deadline, ...rest } = parsed.data;
  return { ...rest, deadline: deadline ? new Date(deadline) : null };
}

export async function createApplication(raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = mbaApplicationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const program = await prisma.mBAProgram.findFirst({ where: { id: data.programId, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  await prisma.mBAApplication.create({ data: { userId, ...data } });
  revalidatePath("/mba-application");
  return { ok: true };
}

export async function updateApplication(id: string, raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = mbaApplicationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const program = await prisma.mBAProgram.findFirst({ where: { id: data.programId, userId } });
  if (!program) return { ok: false, error: "Program not found" };

  const { count } = await prisma.mBAApplication.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Application not found" };

  revalidatePath("/mba-application");
  return { ok: true };
}

export async function deleteApplication(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.mBAApplication.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Application not found" };

  revalidatePath("/mba-application");
  return { ok: true };
}

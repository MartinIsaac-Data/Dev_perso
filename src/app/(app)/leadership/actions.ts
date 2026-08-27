"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { leadershipSchema } from "@/lib/validations/leadership";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof leadershipSchema.safeParse>) {
  if (!parsed.success) return null;
  const { startDate, endDate, ...rest } = parsed.data;
  return {
    ...rest,
    startDate: startDate ? new Date(startDate) : null,
    endDate: endDate ? new Date(endDate) : null,
  };
}

export async function createLeadership(raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = leadershipSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.leadershipExperience.create({ data: { userId, ...data } });
  revalidatePath("/leadership");
  revalidatePath("/");
  return { ok: true };
}

export async function updateLeadership(id: string, raw: Record<string, unknown>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = leadershipSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.leadershipExperience.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/leadership");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteLeadership(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.leadershipExperience.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/leadership");
  revalidatePath("/");
  return { ok: true };
}

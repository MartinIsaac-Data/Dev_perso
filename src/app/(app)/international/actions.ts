"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { internationalSchema } from "@/lib/validations/international";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof internationalSchema.safeParse>) {
  if (!parsed.success) return null;
  const { startDate, endDate, ...rest } = parsed.data;
  return {
    ...rest,
    startDate: startDate ? new Date(startDate) : null,
    endDate: endDate ? new Date(endDate) : null,
  };
}

export async function createInternational(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = internationalSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.internationalExperience.create({ data: { userId, ...data } });
  revalidatePath("/international");
  revalidatePath("/");
  return { ok: true };
}

export async function updateInternational(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = internationalSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.internationalExperience.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/international");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteInternational(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.internationalExperience.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/international");
  revalidatePath("/");
  return { ok: true };
}

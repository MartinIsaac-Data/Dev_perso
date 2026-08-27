"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { educationSchema } from "@/lib/validations/education";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof educationSchema.safeParse>) {
  if (!parsed.success) return null;
  const { startDate, endDate, ...rest } = parsed.data;
  return {
    ...rest,
    startDate: startDate ? new Date(startDate) : null,
    endDate: endDate ? new Date(endDate) : null,
  };
}

export async function createEducation(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = educationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.education.create({ data: { userId, ...data } });
  revalidatePath("/education");
  return { ok: true };
}

export async function updateEducation(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = educationSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.education.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Education record not found" };

  revalidatePath("/education");
  return { ok: true };
}

export async function deleteEducation(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.education.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Education record not found" };

  revalidatePath("/education");
  return { ok: true };
}

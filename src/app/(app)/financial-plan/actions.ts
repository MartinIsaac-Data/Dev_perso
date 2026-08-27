"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { financialPlanSchema, transactionSchema } from "@/lib/validations/financial";

type ActionResult = { ok: boolean; error?: string };

export async function upsertFinancialPlan(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = financialPlanSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const existing = await prisma.financialPlan.findFirst({ where: { userId } });
  if (existing) {
    await prisma.financialPlan.update({ where: { id: existing.id }, data: parsed.data });
  } else {
    await prisma.financialPlan.create({ data: { userId, ...parsed.data } });
  }

  revalidatePath("/financial-plan");
  revalidatePath("/");
  return { ok: true };
}

export async function createTransaction(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = transactionSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message };

  const { date, ...rest } = parsed.data;
  await prisma.financialTransaction.create({ data: { userId, ...rest, date: new Date(date) } });
  revalidatePath("/financial-plan");
  return { ok: true };
}

export async function deleteTransaction(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.financialTransaction.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Not found" };

  revalidatePath("/financial-plan");
  return { ok: true };
}

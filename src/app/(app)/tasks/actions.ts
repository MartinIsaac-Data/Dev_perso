"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { taskSchema } from "@/lib/validations/task";
import { TASK_STATUSES } from "@/lib/labels";

type ActionResult = { ok: boolean; error?: string };

function toData(parsed: ReturnType<typeof taskSchema.safeParse>) {
  if (!parsed.success) return null;
  const { deadline, ...rest } = parsed.data;
  return { ...rest, deadline: deadline ? new Date(deadline) : null };
}

export async function createTask(raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = taskSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  await prisma.task.create({ data: { userId, ...data } });
  revalidatePath("/tasks");
  revalidatePath("/");
  return { ok: true };
}

export async function updateTask(id: string, raw: Record<string, string>): Promise<ActionResult> {
  const userId = await requireUserId();
  const parsed = taskSchema.safeParse(raw);
  const data = toData(parsed);
  if (!data) return { ok: false, error: !parsed.success ? parsed.error.issues[0]?.message : "Invalid data" };

  const { count } = await prisma.task.updateMany({ where: { id, userId }, data });
  if (count === 0) return { ok: false, error: "Task not found" };

  revalidatePath("/tasks");
  revalidatePath("/");
  return { ok: true };
}

export async function deleteTask(id: string): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.task.deleteMany({ where: { id, userId } });
  if (count === 0) return { ok: false, error: "Task not found" };

  revalidatePath("/tasks");
  revalidatePath("/");
  return { ok: true };
}

export async function setTaskStatus(id: string, status: (typeof TASK_STATUSES)[number]): Promise<ActionResult> {
  const userId = await requireUserId();
  const { count } = await prisma.task.updateMany({ where: { id, userId }, data: { status } });
  if (count === 0) return { ok: false, error: "Task not found" };

  revalidatePath("/tasks");
  revalidatePath("/");
  return { ok: true };
}

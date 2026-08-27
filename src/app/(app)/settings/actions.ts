"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { profileSchema } from "@/lib/validations/profile";

export type ProfileActionState = {
  ok: boolean;
  error?: string;
};

export async function updateProfile(
  raw: Record<string, string>,
): Promise<ProfileActionState> {
  const userId = await requireUserId();
  const parsed = profileSchema.safeParse(raw);

  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid data" };
  }

  const { dateOfBirth, ...rest } = parsed.data;

  await prisma.profile.upsert({
    where: { userId },
    create: {
      userId,
      ...rest,
      dateOfBirth: dateOfBirth ? new Date(dateOfBirth) : undefined,
    },
    update: {
      ...rest,
      dateOfBirth: dateOfBirth ? new Date(dateOfBirth) : null,
    },
  });

  await prisma.auditLog.create({
    data: { userId, action: "UPDATE", entity: "Profile" },
  });

  revalidatePath("/settings");
  revalidatePath("/");

  return { ok: true };
}

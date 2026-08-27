"use server";

import { revalidatePath } from "next/cache";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { signOut } from "@/auth";
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

export async function deleteAccount(confirmation: string): Promise<ProfileActionState> {
  const userId = await requireUserId();

  if (confirmation !== "DELETE") {
    return { ok: false, error: 'Type "DELETE" to confirm.' };
  }

  // Every domain table has an onDelete: Cascade foreign key to User, so this
  // removes the account and everything attached to it in one statement.
  await prisma.user.delete({ where: { id: userId } });

  await signOut({ redirectTo: "/login" });
  return { ok: true };
}

import { prisma } from "../lib/prisma";

/**
 * Customers who sign up through the online portal never pick a branch —
 * they don't know or care which physical shop will process their order.
 * Without a fallback, their branchId stays null and the order becomes
 * invisible to every branch-scoped staff member (everyone except
 * SUPER_ADMIN), since list endpoints filter by the caller's branchId.
 * The oldest branch stands in as "the" default for a single/primary
 * location; multi-branch operators can reassign later from the admin.
 */
export async function getDefaultBranchId(): Promise<string | null> {
  const branch = await prisma.branch.findFirst({ orderBy: { createdAt: "asc" } });
  return branch?.id ?? null;
}

/**
 * All branches a staff member may access: every explicit StaffBranch
 * assignment, plus their primary User.branchId (in case it hasn't been
 * synced into an assignment row yet — e.g. a user created before
 * multi-branch existed). Used to populate the JWT at login; the token is
 * the source of truth for the rest of that session (branch reassignment
 * takes effect on next login, not live).
 */
export async function getAccessibleBranchIds(userId: string): Promise<string[]> {
  const [assignments, user] = await Promise.all([
    prisma.staffBranch.findMany({ where: { userId }, select: { branchId: true } }),
    prisma.user.findUnique({ where: { id: userId }, select: { branchId: true } }),
  ]);
  const ids = new Set(assignments.map((a) => a.branchId));
  if (user?.branchId) ids.add(user.branchId);
  return [...ids];
}

/** Replaces a staff member's branch assignments wholesale. */
export async function setStaffBranches(userId: string, branchIds: string[]): Promise<void> {
  const unique = [...new Set(branchIds)];
  await prisma.$transaction([
    prisma.staffBranch.deleteMany({ where: { userId } }),
    ...(unique.length > 0
      ? [prisma.staffBranch.createMany({ data: unique.map((branchId) => ({ userId, branchId })) })]
      : []),
  ]);
}

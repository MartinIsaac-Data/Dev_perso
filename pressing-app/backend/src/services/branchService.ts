import { Prisma } from "@prisma/client";
import { prisma } from "../lib/prisma";

type Db = Prisma.TransactionClient | typeof prisma;

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
export async function getAccessibleBranchIds(userId: string, db: Db = prisma): Promise<string[]> {
  const [assignments, user] = await Promise.all([
    db.staffBranch.findMany({ where: { userId }, select: { branchId: true } }),
    db.user.findUnique({ where: { id: userId }, select: { branchId: true } }),
  ]);
  const ids = new Set(assignments.map((a) => a.branchId));
  if (user?.branchId) ids.add(user.branchId);
  return [...ids];
}

/**
 * Replaces a staff member's branch assignments wholesale. Pass a
 * transaction client (`db`) when this needs to be atomic with the User
 * row it's assigning branches to — e.g. employee creation, where a
 * standalone $transaction here would let the User commit even if this
 * step then failed.
 */
export async function setStaffBranches(userId: string, branchIds: string[], db: Db = prisma): Promise<void> {
  const unique = [...new Set(branchIds)];
  const run = async (client: Db) => {
    await client.staffBranch.deleteMany({ where: { userId } });
    if (unique.length > 0) {
      await client.staffBranch.createMany({ data: unique.map((branchId) => ({ userId, branchId })) });
    }
  };
  // Already inside a transaction (the caller passed a tx client): just run —
  // wrapping again would fail, since a Prisma.TransactionClient has no
  // $transaction of its own. Called standalone (the default `prisma`): wrap
  // ourselves so delete+recreate stays atomic on its own.
  if (db === prisma) {
    await prisma.$transaction((tx) => run(tx));
  } else {
    await run(db);
  }
}

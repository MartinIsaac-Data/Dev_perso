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

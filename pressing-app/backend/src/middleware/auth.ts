import { NextFunction, Request, Response } from "express";
import { Role } from "@prisma/client";
import { verifyToken } from "../lib/jwt";
import { Permission, roleHasPermission } from "../lib/permissions";
import { prisma } from "../lib/prisma";
import { ApiError } from "./errorHandler";

export interface AuthUser {
  id: string;
  role: Role;
  branchId: string | null;
  branchIds: string[];
  activeBranchId: string | null;
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  if (!header || !header.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Authentication required" });
  }
  try {
    const payload = verifyToken(header.slice("Bearer ".length));
    const branchIds = payload.branchIds ?? (payload.branchId ? [payload.branchId] : []);

    const requestedBranch = req.headers["x-active-branch"];
    let activeBranchId: string | null = null;
    if (typeof requestedBranch === "string" && requestedBranch.length > 0) {
      if (payload.role !== "SUPER_ADMIN" && !branchIds.includes(requestedBranch)) {
        return res.status(403).json({ error: "Not assigned to this branch" });
      }
      activeBranchId = requestedBranch;
    }

    req.user = { id: payload.sub, role: payload.role, branchId: payload.branchId, branchIds, activeBranchId };
    next();
  } catch {
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}

export function requirePermission(permission: Permission) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.user) return res.status(401).json({ error: "Authentication required" });
    if (!roleHasPermission(req.user.role, permission)) {
      return res.status(403).json({ error: "Insufficient permissions" });
    }
    next();
  };
}

/**
 * Scopes a Prisma `where` filter to the branch(es) the caller may see.
 * SUPER_ADMIN sees every branch unless they've narrowed the view via the
 * X-Active-Branch header. Everyone else is scoped to their assigned
 * branches (possibly several, for multi-agency staff), narrowed to one
 * when they've picked a specific branch in the UI switcher. A staff
 * member with zero assignments gets an impossible filter rather than an
 * unscoped `{}`, so they see nothing instead of everything.
 */
export function branchScope(user: AuthUser): { branchId?: string | { in: string[] } } {
  if (user.role === "SUPER_ADMIN") {
    return user.activeBranchId ? { branchId: user.activeBranchId } : {};
  }
  if (user.activeBranchId) return { branchId: user.activeBranchId };
  if (user.branchIds.length === 0) return { branchId: "__no_access__" };
  if (user.branchIds.length === 1) return { branchId: user.branchIds[0] };
  return { branchId: { in: user.branchIds } };
}

export async function loadFreshUser(userId: string) {
  return prisma.user.findUnique({ where: { id: userId } });
}

/**
 * Throws 403 unless `user`'s branch scope covers `resourceBranchId` — the
 * same rule branchScope() encodes for list queries, applied to a single
 * already-fetched resource (an order, a payment intent, an order item's
 * photo) before returning or mutating it.
 */
export function assertBranchAccess(user: AuthUser, resourceBranchId: string | null) {
  const scope = branchScope(user);
  if (!scope.branchId) return; // unscoped (SUPER_ADMIN with no active branch)
  if (!resourceBranchId) throw new ApiError(403, "Accès non autorisé à cette ressource");
  if (typeof scope.branchId === "string" && scope.branchId !== resourceBranchId) {
    throw new ApiError(403, "Accès non autorisé à cette ressource");
  }
  if (typeof scope.branchId === "object" && !scope.branchId.in.includes(resourceBranchId)) {
    throw new ApiError(403, "Accès non autorisé à cette ressource");
  }
}

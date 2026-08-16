import { NextFunction, Request, Response } from "express";
import { Role } from "@prisma/client";
import { verifyToken } from "../lib/jwt";
import { Permission, roleHasPermission } from "../lib/permissions";
import { prisma } from "../lib/prisma";

export interface AuthUser {
  id: string;
  role: Role;
  branchId: string | null;
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
    req.user = { id: payload.sub, role: payload.role, branchId: payload.branchId };
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
 * Scopes a Prisma `where` filter to the caller's branch, unless they are
 * SUPER_ADMIN (who can see every branch). Applied on list endpoints for
 * branch-owned resources so a MANAGER never sees another shop's data.
 */
export function branchScope(user: AuthUser): { branchId?: string } {
  if (user.role === "SUPER_ADMIN") return {};
  return user.branchId ? { branchId: user.branchId } : {};
}

export async function loadFreshUser(userId: string) {
  return prisma.user.findUnique({ where: { id: userId } });
}

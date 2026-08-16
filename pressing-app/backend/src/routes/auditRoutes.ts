import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { listAuditLogs } from "../controllers/auditController";

export const auditRoutes = Router();
auditRoutes.use(requireAuth);
auditRoutes.get("/", requirePermission("audit:read"), asyncHandler(listAuditLogs));

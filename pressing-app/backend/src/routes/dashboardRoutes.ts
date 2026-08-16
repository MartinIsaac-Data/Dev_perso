import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { getDashboard } from "../controllers/dashboardController";

export const dashboardRoutes = Router();
dashboardRoutes.use(requireAuth);
dashboardRoutes.get("/", requirePermission("dashboard:read"), asyncHandler(getDashboard));

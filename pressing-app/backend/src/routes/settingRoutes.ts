import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { getSettings, updateSettings } from "../controllers/settingController";

export const settingRoutes = Router();
settingRoutes.use(requireAuth);

settingRoutes.get("/", requirePermission("settings:read"), asyncHandler(getSettings));
settingRoutes.put("/", requirePermission("settings:write"), asyncHandler(updateSettings));

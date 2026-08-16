import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  createService,
  deleteService,
  listServices,
  updateService,
} from "../controllers/serviceController";

export const serviceRoutes = Router();
serviceRoutes.use(requireAuth);

serviceRoutes.get("/", requirePermission("services:read"), asyncHandler(listServices));
serviceRoutes.post("/", requirePermission("services:write"), asyncHandler(createService));
serviceRoutes.put("/:id", requirePermission("services:write"), asyncHandler(updateService));
serviceRoutes.delete("/:id", requirePermission("services:write"), asyncHandler(deleteService));

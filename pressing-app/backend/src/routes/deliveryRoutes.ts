import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { createDelivery, listDeliveries, updateDelivery } from "../controllers/deliveryController";

export const deliveryRoutes = Router();
deliveryRoutes.use(requireAuth);

deliveryRoutes.get("/", requirePermission("deliveries:read"), asyncHandler(listDeliveries));
deliveryRoutes.post("/", requirePermission("deliveries:write"), asyncHandler(createDelivery));
deliveryRoutes.put("/:id", requirePermission("deliveries:write"), asyncHandler(updateDelivery));

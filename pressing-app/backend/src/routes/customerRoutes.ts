import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  createCustomer,
  deactivateCustomer,
  getCustomer,
  listCustomers,
  updateCustomer,
} from "../controllers/customerController";

export const customerRoutes = Router();
customerRoutes.use(requireAuth);

customerRoutes.get("/", requirePermission("customers:read"), asyncHandler(listCustomers));
customerRoutes.get("/:id", requirePermission("customers:read"), asyncHandler(getCustomer));
customerRoutes.post("/", requirePermission("customers:write"), asyncHandler(createCustomer));
customerRoutes.put("/:id", requirePermission("customers:write"), asyncHandler(updateCustomer));
customerRoutes.delete(
  "/:id",
  requirePermission("customers:write"),
  asyncHandler(deactivateCustomer)
);

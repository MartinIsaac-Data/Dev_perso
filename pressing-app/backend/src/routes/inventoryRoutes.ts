import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  addInventoryTransaction,
  createProduct,
  listProducts,
  updateProduct,
} from "../controllers/inventoryController";

export const inventoryRoutes = Router();
inventoryRoutes.use(requireAuth);

inventoryRoutes.get("/", requirePermission("inventory:read"), asyncHandler(listProducts));
inventoryRoutes.post("/", requirePermission("inventory:write"), asyncHandler(createProduct));
inventoryRoutes.put("/:id", requirePermission("inventory:write"), asyncHandler(updateProduct));
inventoryRoutes.post(
  "/:id/transactions",
  requirePermission("inventory:write"),
  asyncHandler(addInventoryTransaction)
);

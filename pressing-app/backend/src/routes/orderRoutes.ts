import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  addPayment,
  createOrder,
  getOrder,
  getTicket,
  listOrders,
  updateOrder,
  updateOrderStatus,
} from "../controllers/orderController";

export const orderRoutes = Router();
orderRoutes.use(requireAuth);

orderRoutes.get("/", requirePermission("orders:read"), asyncHandler(listOrders));
orderRoutes.get("/:id", requirePermission("orders:read"), asyncHandler(getOrder));
orderRoutes.get("/:id/ticket", requirePermission("orders:read"), asyncHandler(getTicket));
orderRoutes.post("/", requirePermission("orders:write"), asyncHandler(createOrder));
orderRoutes.put("/:id", requirePermission("orders:write"), asyncHandler(updateOrder));
orderRoutes.post("/:id/status", requirePermission("orders:status"), asyncHandler(updateOrderStatus));
orderRoutes.post("/:id/payments", requirePermission("payments:write"), asyncHandler(addPayment));

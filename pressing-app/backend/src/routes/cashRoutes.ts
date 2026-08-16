import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  addCashTransaction,
  closeRegister,
  getCurrentRegister,
  listCashRegisters,
  openRegister,
} from "../controllers/cashController";

export const cashRoutes = Router();
cashRoutes.use(requireAuth);

cashRoutes.get("/", requirePermission("cash:read"), asyncHandler(listCashRegisters));
cashRoutes.get("/current", requirePermission("cash:read"), asyncHandler(getCurrentRegister));
cashRoutes.post("/open", requirePermission("cash:manage"), asyncHandler(openRegister));
cashRoutes.post("/:id/close", requirePermission("cash:manage"), asyncHandler(closeRegister));
cashRoutes.post("/:id/transactions", requirePermission("cash:manage"), asyncHandler(addCashTransaction));

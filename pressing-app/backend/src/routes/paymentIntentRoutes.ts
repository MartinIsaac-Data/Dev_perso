import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { getPaymentIntentStatusForStaff } from "../controllers/paymentIntentController";

export const paymentIntentRoutes = Router();
paymentIntentRoutes.use(requireAuth);

paymentIntentRoutes.get("/:id", requirePermission("payments:write"), asyncHandler(getPaymentIntentStatusForStaff));

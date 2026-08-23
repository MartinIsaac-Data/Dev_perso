import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireCustomerAuth } from "../middleware/customerAuth";
import {
  createOwnOrder,
  getOwnOrder,
  getOwnPaymentIntentStatus,
  initiateOwnMobileMoneyPayment,
  listActiveServices,
  listOwnOrders,
} from "../controllers/portalOrderController";

export const portalRoutes = Router();

portalRoutes.get("/services", asyncHandler(listActiveServices));

portalRoutes.use(requireCustomerAuth);
portalRoutes.get("/orders", asyncHandler(listOwnOrders));
portalRoutes.post("/orders", asyncHandler(createOwnOrder));
portalRoutes.get("/orders/:id", asyncHandler(getOwnOrder));
portalRoutes.post("/orders/:id/mobile-money", asyncHandler(initiateOwnMobileMoneyPayment));
portalRoutes.get("/payment-intents/:intentId", asyncHandler(getOwnPaymentIntentStatus));

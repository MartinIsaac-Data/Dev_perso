import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { mtnMomoWebhook, orangeMoneyWebhook } from "../controllers/webhookController";

// Public — called by the mobile money providers themselves, not by our
// frontend. No requireAuth: these carry their own shared-secret check.
export const webhookRoutes = Router();

webhookRoutes.post("/orange-money", asyncHandler(orangeMoneyWebhook));
webhookRoutes.post("/mtn-momo", asyncHandler(mtnMomoWebhook));

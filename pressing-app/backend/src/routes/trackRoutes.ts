import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { trackOrder } from "../controllers/trackController";

// Public — no auth. Used by the order-tracking page any customer can reach
// without an administration login (spec section 12).
export const trackRoutes = Router();
trackRoutes.get("/", asyncHandler(trackOrder));

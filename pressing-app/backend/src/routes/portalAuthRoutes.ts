import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireCustomerAuth } from "../middleware/customerAuth";
import { forgotPassword, login, me, register, resetPassword } from "../controllers/portalAuthController";

export const portalAuthRoutes = Router();

portalAuthRoutes.post("/register", asyncHandler(register));
portalAuthRoutes.post("/login", asyncHandler(login));
portalAuthRoutes.post("/forgot-password", asyncHandler(forgotPassword));
portalAuthRoutes.post("/reset-password", asyncHandler(resetPassword));
portalAuthRoutes.get("/me", requireCustomerAuth, asyncHandler(me));

import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireCustomerAuth } from "../middleware/customerAuth";
import { login, me, register } from "../controllers/portalAuthController";

export const portalAuthRoutes = Router();

portalAuthRoutes.post("/register", asyncHandler(register));
portalAuthRoutes.post("/login", asyncHandler(login));
portalAuthRoutes.get("/me", requireCustomerAuth, asyncHandler(me));

import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { createEmployee, listEmployees, updateEmployee } from "../controllers/userController";

export const userRoutes = Router();
userRoutes.use(requireAuth);

userRoutes.get("/", requirePermission("employees:read"), asyncHandler(listEmployees));
userRoutes.post("/", requirePermission("employees:write"), asyncHandler(createEmployee));
userRoutes.put("/:id", requirePermission("employees:write"), asyncHandler(updateEmployee));

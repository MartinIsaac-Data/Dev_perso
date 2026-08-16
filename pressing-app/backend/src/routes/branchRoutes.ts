import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { createBranch, listBranches, updateBranch } from "../controllers/branchController";

export const branchRoutes = Router();
branchRoutes.use(requireAuth);

branchRoutes.get("/", asyncHandler(listBranches));
branchRoutes.post("/", requirePermission("branches:manage"), asyncHandler(createBranch));
branchRoutes.put("/:id", requirePermission("branches:manage"), asyncHandler(updateBranch));

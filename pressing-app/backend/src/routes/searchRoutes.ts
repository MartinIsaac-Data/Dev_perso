import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth } from "../middleware/auth";
import { globalSearch } from "../controllers/searchController";

export const searchRoutes = Router();
searchRoutes.use(requireAuth);
searchRoutes.get("/", asyncHandler(globalSearch));

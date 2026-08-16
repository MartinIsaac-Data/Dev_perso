import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import { createExpense, listExpenses } from "../controllers/expenseController";

export const expenseRoutes = Router();
expenseRoutes.use(requireAuth);

expenseRoutes.get("/", requirePermission("expenses:read"), asyncHandler(listExpenses));
expenseRoutes.post("/", requirePermission("expenses:write"), asyncHandler(createExpense));

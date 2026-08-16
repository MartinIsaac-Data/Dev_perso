import { Router } from "express";
import { asyncHandler } from "../middleware/asyncHandler";
import { requireAuth, requirePermission } from "../middleware/auth";
import {
  clientsReport,
  employeesReport,
  financeReport,
  operationsReport,
  salesReport,
  servicesReport,
} from "../controllers/reportController";

export const reportRoutes = Router();
reportRoutes.use(requireAuth, requirePermission("reports:read"));

reportRoutes.get("/sales", asyncHandler(salesReport));
reportRoutes.get("/clients", asyncHandler(clientsReport));
reportRoutes.get("/services", asyncHandler(servicesReport));
reportRoutes.get("/employees", asyncHandler(employeesReport));
reportRoutes.get("/finance", asyncHandler(financeReport));
reportRoutes.get("/operations", asyncHandler(operationsReport));

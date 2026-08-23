import express from "express";
import cors from "cors";
import helmet from "helmet";
import compression from "compression";
import morgan from "morgan";
import rateLimit from "express-rate-limit";
import { authRoutes } from "./routes/authRoutes";
import { customerRoutes } from "./routes/customerRoutes";
import { serviceRoutes } from "./routes/serviceRoutes";
import { orderRoutes } from "./routes/orderRoutes";
import { trackRoutes } from "./routes/trackRoutes";
import { deliveryRoutes } from "./routes/deliveryRoutes";
import { cashRoutes } from "./routes/cashRoutes";
import { expenseRoutes } from "./routes/expenseRoutes";
import { inventoryRoutes } from "./routes/inventoryRoutes";
import { dashboardRoutes } from "./routes/dashboardRoutes";
import { userRoutes } from "./routes/userRoutes";
import { settingRoutes } from "./routes/settingRoutes";
import { auditRoutes } from "./routes/auditRoutes";
import { branchRoutes } from "./routes/branchRoutes";
import { reportRoutes } from "./routes/reportRoutes";
import { searchRoutes } from "./routes/searchRoutes";
import { portalAuthRoutes } from "./routes/portalAuthRoutes";
import { portalRoutes } from "./routes/portalRoutes";
import { paymentIntentRoutes } from "./routes/paymentIntentRoutes";
import { webhookRoutes } from "./routes/webhookRoutes";
import { orderItemPhotoRoutes } from "./routes/orderItemPhotoRoutes";
import { errorHandler } from "./middleware/errorHandler";

export function createApp() {
  const app = express();

  app.use(helmet());
  app.use(
    cors({
      origin: process.env.CORS_ORIGIN?.split(",") ?? "*",
      credentials: true,
    })
  );
  app.use(compression());
  app.use(express.json({ limit: "5mb" }));
  app.use(morgan(process.env.NODE_ENV === "test" ? "silent" : "dev"));

  const apiLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    limit: 600,
    standardHeaders: true,
    legacyHeaders: false,
  });
  const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    limit: 20,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: "Too many login attempts, try again later" },
  });
  app.use("/api", apiLimiter);
  app.use("/api/auth/login", authLimiter);
  app.use("/api/portal-auth/login", authLimiter);
  app.use("/api/portal-auth/register", authLimiter);

  app.get("/api/health", (_req, res) => res.json({ status: "ok" }));

  app.use("/api/auth", authRoutes);
  app.use("/api/portal-auth", portalAuthRoutes);
  app.use("/api/portal", portalRoutes);
  app.use("/api/customers", customerRoutes);
  app.use("/api/services", serviceRoutes);
  app.use("/api/orders", orderRoutes);
  app.use("/api/track", trackRoutes);
  app.use("/api/deliveries", deliveryRoutes);
  app.use("/api/cash-registers", cashRoutes);
  app.use("/api/expenses", expenseRoutes);
  app.use("/api/inventory", inventoryRoutes);
  app.use("/api/dashboard", dashboardRoutes);
  app.use("/api/employees", userRoutes);
  app.use("/api/settings", settingRoutes);
  app.use("/api/audit-logs", auditRoutes);
  app.use("/api/branches", branchRoutes);
  app.use("/api/reports", reportRoutes);
  app.use("/api/search", searchRoutes);
  app.use("/api/payment-intents", paymentIntentRoutes);
  app.use("/api/webhooks", webhookRoutes);
  app.use("/api/order-items", orderItemPhotoRoutes);

  app.use(errorHandler);

  return app;
}

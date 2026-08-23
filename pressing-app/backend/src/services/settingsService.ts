import { prisma } from "../lib/prisma";

/**
 * Settings are stored as generic key/value rows (see settingController.ts).
 * These two booleans gate mobile money payments and SMS/WhatsApp
 * notifications into "simulation mode": real providers are skipped and a
 * fake success is generated instead, so the app can be demoed live without
 * spending real money or real SMS credit. Defaults to true so a fresh
 * deployment is safe-by-default even before anyone visits Settings.
 */
export async function isSimulationMode(kind: "payments" | "notifications"): Promise<boolean> {
  const key = kind === "payments" ? "paymentsSimulationMode" : "notificationsSimulationMode";
  const row = await prisma.setting.findUnique({ where: { key } });
  if (!row) return true;
  return row.value !== false;
}

import { z } from "zod";

export const cashOpenSchema = z.object({
  branchId: z.string().uuid().optional().nullable(),
  openingBalance: z.coerce.number().nonnegative().default(0),
});

export const cashCloseSchema = z.object({
  closingBalanceActual: z.coerce.number().nonnegative(),
});

export const cashTransactionSchema = z.object({
  type: z.enum(["SALE", "EXPENSE", "REFUND", "ADJUSTMENT", "DEPOSIT", "WITHDRAWAL"]),
  amount: z.coerce.number(),
  method: z.enum(["CASH", "MOBILE_MONEY", "CARD", "BANK_TRANSFER", "OTHER"]).default("CASH"),
  description: z.string().optional().nullable(),
});

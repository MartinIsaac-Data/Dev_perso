import { z } from "zod";

export const expenseCreateSchema = z.object({
  branchId: z.string().uuid().optional().nullable(),
  date: z.coerce.date().default(() => new Date()),
  amount: z.coerce.number().positive(),
  category: z.enum([
    "CHEMICALS",
    "WATER",
    "ELECTRICITY",
    "TRANSPORT",
    "MAINTENANCE",
    "SALARIES",
    "DELIVERY",
    "RENT",
    "OTHER",
  ]),
  description: z.string().optional().nullable(),
  paymentMethod: z.enum(["CASH", "ORANGE_MONEY", "MTN_MOMO", "CARD", "BANK_TRANSFER", "OTHER"]).default("CASH"),
  receiptUrl: z.string().optional().nullable(),
});

import { z } from "zod";

export const paymentIntentInitiateSchema = z.object({
  provider: z.enum(["ORANGE_MONEY", "MTN_MOMO"]),
  phone: z.string().min(8),
  amount: z.coerce.number().positive().optional(),
});

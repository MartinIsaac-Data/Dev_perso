import { z } from "zod";

export const serviceCreateSchema = z.object({
  name: z.string().min(2),
  description: z.string().optional().nullable(),
  category: z.string().min(1),
  price: z.coerce.number().nonnegative(),
  expressPrice: z.coerce.number().nonnegative().optional().nullable(),
  standardDurationHours: z.coerce.number().int().positive().default(48),
  expressDurationHours: z.coerce.number().int().positive().optional().nullable(),
  active: z.boolean().default(true),
});

export const serviceUpdateSchema = serviceCreateSchema.partial();

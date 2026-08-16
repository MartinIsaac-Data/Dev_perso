import { z } from "zod";

export const customerCreateSchema = z.object({
  fullName: z.string().min(2),
  phone: z.string().min(6),
  email: z.string().email().optional().nullable(),
  address: z.string().optional().nullable(),
  birthDate: z.coerce.date().optional().nullable(),
  type: z.enum(["INDIVIDUAL", "COMPANY", "VIP"]).default("INDIVIDUAL"),
  notes: z.string().optional().nullable(),
  branchId: z.string().uuid().optional().nullable(),
});

export const customerUpdateSchema = customerCreateSchema.partial();

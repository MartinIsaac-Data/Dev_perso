import { z } from "zod";

export const userCreateSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
  fullName: z.string().min(2),
  phone: z.string().optional().nullable(),
  role: z.enum(["SUPER_ADMIN", "ADMIN", "MANAGER", "CASHIER", "OPERATOR", "DELIVERY"]),
  position: z.string().optional().nullable(),
  hireDate: z.coerce.date().optional().nullable(),
  branchId: z.string().uuid().optional().nullable(),
});

export const userUpdateSchema = z.object({
  fullName: z.string().min(2).optional(),
  phone: z.string().optional().nullable(),
  role: z.enum(["SUPER_ADMIN", "ADMIN", "MANAGER", "CASHIER", "OPERATOR", "DELIVERY"]).optional(),
  position: z.string().optional().nullable(),
  active: z.boolean().optional(),
  branchId: z.string().uuid().optional().nullable(),
  password: z.string().min(6).optional(),
});

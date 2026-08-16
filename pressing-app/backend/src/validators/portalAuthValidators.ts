import { z } from "zod";

export const portalRegisterSchema = z.object({
  fullName: z.string().min(2),
  phone: z.string().min(6),
  email: z.string().email().optional().nullable(),
  address: z.string().optional().nullable(),
  password: z.string().min(6),
});

export const portalLoginSchema = z.object({
  phone: z.string().min(6),
  password: z.string().min(1),
});

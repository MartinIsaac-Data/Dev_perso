import { z } from "zod";

export const deliveryCreateSchema = z.object({
  orderId: z.string().uuid(),
  type: z.enum(["PICKUP", "DELIVERY"]).default("DELIVERY"),
  address: z.string().optional().nullable(),
  neighborhood: z.string().optional().nullable(),
  city: z.string().optional().nullable(),
  phone: z.string().optional().nullable(),
  delivererId: z.string().uuid().optional().nullable(),
  fee: z.coerce.number().nonnegative().default(0),
  scheduledDate: z.coerce.date().optional().nullable(),
});

export const deliveryUpdateSchema = z.object({
  delivererId: z.string().uuid().optional().nullable(),
  status: z.enum(["PENDING", "ASSIGNED", "PICKED_UP", "IN_TRANSIT", "DELIVERED", "FAILED"]).optional(),
  scheduledDate: z.coerce.date().optional().nullable(),
  address: z.string().optional().nullable(),
  neighborhood: z.string().optional().nullable(),
  city: z.string().optional().nullable(),
  phone: z.string().optional().nullable(),
  fee: z.coerce.number().nonnegative().optional(),
});

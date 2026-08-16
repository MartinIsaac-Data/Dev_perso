import { z } from "zod";

export const orderItemSchema = z.object({
  category: z.enum([
    "SHIRT",
    "TSHIRT",
    "PANTS",
    "JEANS",
    "SUIT",
    "JACKET",
    "DRESS",
    "SKIRT",
    "COAT",
    "BEDSHEET",
    "BLANKET",
    "CURTAIN",
    "SHOES",
    "BAG",
    "OTHER",
  ]),
  articleType: z.string().min(1),
  quantity: z.coerce.number().int().positive().default(1),
  color: z.string().optional().nullable(),
  brand: z.string().optional().nullable(),
  size: z.string().optional().nullable(),
  conditionAtReceipt: z.string().optional().nullable(),
  existingStains: z.string().optional().nullable(),
  existingDamages: z.string().optional().nullable(),
  specialInstructions: z.string().optional().nullable(),
  photoUrl: z.string().optional().nullable(),
  serviceId: z.string().uuid(),
  isExpress: z.boolean().default(false),
});

export const orderCreateSchema = z.object({
  customerId: z.string().uuid(),
  branchId: z.string().uuid().optional().nullable(),
  priority: z.enum(["NORMAL", "EXPRESS"]).default("NORMAL"),
  estimatedReadyDate: z.coerce.date().optional().nullable(),
  discount: z.coerce.number().nonnegative().default(0),
  deliveryFee: z.coerce.number().nonnegative().default(0),
  notes: z.string().optional().nullable(),
  items: z.array(orderItemSchema).min(1, "At least one article is required"),
  initialPayment: z
    .object({
      amount: z.coerce.number().positive(),
      method: z.enum(["CASH", "MOBILE_MONEY", "CARD", "BANK_TRANSFER", "OTHER"]),
      reference: z.string().optional().nullable(),
    })
    .optional()
    .nullable(),
});

export const orderUpdateSchema = z.object({
  priority: z.enum(["NORMAL", "EXPRESS"]).optional(),
  estimatedReadyDate: z.coerce.date().optional().nullable(),
  discount: z.coerce.number().nonnegative().optional(),
  deliveryFee: z.coerce.number().nonnegative().optional(),
  notes: z.string().optional().nullable(),
});

export const orderStatusSchema = z.object({
  status: z.enum([
    "RECEIVED",
    "INSPECTION",
    "PROCESSING",
    "QUALITY_CHECK",
    "READY",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "COMPLETED",
    "CANCELLED",
  ]),
  note: z.string().optional().nullable(),
});

export const paymentCreateSchema = z.object({
  amount: z.coerce.number().positive(),
  method: z.enum(["CASH", "MOBILE_MONEY", "CARD", "BANK_TRANSFER", "OTHER"]),
  reference: z.string().optional().nullable(),
  notes: z.string().optional().nullable(),
});

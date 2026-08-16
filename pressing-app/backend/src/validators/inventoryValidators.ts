import { z } from "zod";

export const productCreateSchema = z.object({
  name: z.string().min(2),
  category: z.enum([
    "DETERGENT",
    "SOFTENER",
    "STAIN_REMOVER",
    "BLEACH",
    "PACKAGING",
    "BAGS",
    "HANGERS",
    "LABELS",
    "OTHER",
  ]),
  currentStock: z.coerce.number().nonnegative().default(0),
  minStock: z.coerce.number().nonnegative().default(0),
  unit: z.string().min(1),
  purchasePrice: z.coerce.number().nonnegative().optional().nullable(),
  supplier: z.string().optional().nullable(),
  branchId: z.string().uuid().optional().nullable(),
});

export const productUpdateSchema = productCreateSchema.partial();

export const inventoryTransactionSchema = z.object({
  type: z.enum(["ENTRY", "EXIT", "ADJUSTMENT"]),
  quantity: z.coerce.number(),
  reason: z.string().optional().nullable(),
});

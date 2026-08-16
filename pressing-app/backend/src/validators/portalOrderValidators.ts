import { z } from "zod";
import { orderItemSchema } from "./orderValidators";

export const portalOrderCreateSchema = z.object({
  priority: z.enum(["NORMAL", "EXPRESS"]).default("NORMAL"),
  notes: z.string().optional().nullable(),
  items: z.array(orderItemSchema).min(1, "Ajoutez au moins un article"),
  fulfillment: z.enum(["PICKUP", "DELIVERY"]).default("PICKUP"),
  deliveryAddress: z.string().optional().nullable(),
  deliveryNeighborhood: z.string().optional().nullable(),
  deliveryCity: z.string().optional().nullable(),
});

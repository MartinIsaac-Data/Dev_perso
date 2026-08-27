import { z } from "zod";
import { INTERNATIONAL_EXPOSURE_TYPES } from "@/lib/labels";

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

const optionalString = z
  .string()
  .trim()
  .max(1000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

export const internationalSchema = z.object({
  country: z.string().trim().min(1, "Country is required").max(200),
  company: optionalString,
  project: optionalString,
  role: optionalString,
  type: z.enum(INTERNATIONAL_EXPOSURE_TYPES),
  startDate: optionalDate,
  endDate: optionalDate,
  team: optionalString,
  responsibilities: optionalString,
});

export type InternationalFormValues = z.infer<typeof internationalSchema>;

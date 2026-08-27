import { z } from "zod";
import { CERTIFICATION_STATUSES } from "@/lib/labels";

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

export const certificationSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(300),
  provider: z.string().trim().min(1, "Provider is required").max(200),
  category: optionalString,
  status: z.enum(CERTIFICATION_STATUSES),
  startDate: optionalDate,
  examDate: optionalDate,
  completionDate: optionalDate,
  score: optionalString,
  cost: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  currency: z.string().trim().min(1).max(10).default("EUR"),
  expirationDate: optionalDate,
  certificateUrl: optionalString,
  notes: optionalString,
});

export type CertificationFormValues = z.infer<typeof certificationSchema>;

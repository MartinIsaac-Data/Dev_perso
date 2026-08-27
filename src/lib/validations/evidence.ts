import { z } from "zod";
import { EVIDENCE_TYPES } from "@/lib/labels";

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

const optionalString = z
  .string()
  .trim()
  .max(2000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

const optionalId = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined || v === "none" ? undefined : v));

const csvList = z
  .string()
  .optional()
  .transform((v) =>
    (v ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );

export const evidenceSchema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  type: z.enum(EVIDENCE_TYPES),
  date: optionalDate,
  description: optionalString,
  tags: csvList,
  fileUrl: optionalString,
  projectId: optionalId,
  certificationId: optionalId,
});

export type EvidenceFormValues = z.infer<typeof evidenceSchema>;

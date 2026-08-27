import { z } from "zod";
import { SKILL_CATEGORIES, SKILL_LEVELS } from "@/lib/labels";

export const skillSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  category: z.enum(SKILL_CATEGORIES),
  currentLevel: z.enum(SKILL_LEVELS),
  targetLevel: z.enum(SKILL_LEVELS),
  notes: z
    .string()
    .trim()
    .max(2000)
    .optional()
    .transform((v) => (v === "" ? undefined : v)),
});

export type SkillFormValues = z.infer<typeof skillSchema>;

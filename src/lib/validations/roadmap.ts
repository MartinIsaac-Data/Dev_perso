import { z } from "zod";
import { MILESTONE_STATUSES, PRIORITIES } from "@/lib/labels";

const optionalString = z
  .string()
  .trim()
  .max(2000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

const optionalDate = z
  .string()
  .optional()
  .transform((v) => (v === "" || v === undefined ? undefined : v));

export const roadmapSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  startYear: z.string().min(1).transform(Number),
  endYear: z.string().min(1).transform(Number),
});

export const milestoneSchema = z.object({
  year: z.string().min(1).transform(Number),
  title: z.string().trim().min(1, "Title is required").max(300),
  objective: optionalString,
  deadline: optionalDate,
  status: z.enum(MILESTONE_STATUSES),
  priority: z.enum(PRIORITIES),
  kpi: optionalString,
  dependsOnId: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined || v === "none" ? undefined : v)),
});

export type RoadmapFormValues = z.infer<typeof roadmapSchema>;
export type MilestoneFormValues = z.infer<typeof milestoneSchema>;

import { z } from "zod";
import { STORY_TAGS } from "@/lib/labels";

const optionalString = z
  .string()
  .trim()
  .max(4000)
  .optional()
  .transform((v) => (v === "" ? undefined : v));

export const storySchema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  situation: optionalString,
  task: optionalString,
  action: optionalString,
  result: optionalString,
  reflection: optionalString,
  tags: z.array(z.enum(STORY_TAGS)).default([]),
  mbaRelevanceScore: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  projectId: z
    .string()
    .optional()
    .transform((v) => (v === "" || v === undefined || v === "none" ? undefined : v)),
});

export type StoryFormValues = z.infer<typeof storySchema>;

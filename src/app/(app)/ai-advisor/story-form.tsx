"use client";

import { useState, useTransition } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { STORY_TAGS, humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { createStory, updateStory } from "@/app/(app)/ai-advisor/story-actions";

export type StoryValues = {
  title: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  reflection: string;
  tags: (typeof STORY_TAGS)[number][];
  mbaRelevanceScore: string;
  projectId: string;
};

const emptyValues: StoryValues = {
  title: "",
  situation: "",
  task: "",
  action: "",
  result: "",
  reflection: "",
  tags: [],
  mbaRelevanceScore: "",
  projectId: "none",
};

export function StoryFormDialog({
  mode,
  storyId,
  initialValues,
  projects,
}: {
  mode: "create" | "edit";
  storyId?: string;
  initialValues?: StoryValues;
  projects: { id: string; name: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();
  const { register, handleSubmit, watch, setValue } = useForm<StoryValues>({
    defaultValues: initialValues ?? emptyValues,
  });
  const tags = watch("tags");
  const projectId = watch("projectId");

  const toggleTag = (tag: (typeof STORY_TAGS)[number]) => {
    setValue("tags", tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag]);
  };

  const onSubmit = handleSubmit((values) => {
    startTransition(async () => {
      const result = mode === "create" ? await createStory(values) : await updateStory(storyId!, values);
      if (result.ok) {
        toast.success(mode === "create" ? "Story saved" : "Updated");
        setOpen(false);
      } else {
        toast.error(result.error ?? "Something went wrong");
      }
    });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {mode === "create" ? (
          <Button size="sm">
            <Plus className="size-4" /> Add story
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="size-8" aria-label="Edit">
            <Pencil className="size-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add story" : "Edit story"}</DialogTitle>
          <DialogDescription>
            STAR format — situation, task, action, result. Only what actually happened; the AI Advisor
            will draw on this without inventing anything new.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="title">Title</Label>
            <Input id="title" {...register("title", { required: true })} />
          </div>
          {projects.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label>Related project</Label>
              <Select value={projectId} onValueChange={(v) => setValue("projectId", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="situation">Situation</Label>
            <Textarea id="situation" rows={2} {...register("situation")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task">Task</Label>
            <Textarea id="task" rows={2} {...register("task")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="action">Action</Label>
            <Textarea id="action" rows={2} {...register("action")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="result">Result</Label>
            <Textarea id="result" rows={2} {...register("result")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reflection">Reflection</Label>
            <Textarea id="reflection" rows={2} {...register("reflection")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Tags</Label>
            <div className="flex flex-wrap gap-1.5">
              {STORY_TAGS.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  className={cn("cursor-pointer", "focus:outline-none")}
                >
                  <Badge variant={tags.includes(tag) ? "default" : "outline"}>{humanize(tag)}</Badge>
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mbaRelevanceScore">MBA relevance (0-100, self-assessed)</Label>
            <Input id="mbaRelevanceScore" type="number" min="0" max="100" {...register("mbaRelevanceScore")} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

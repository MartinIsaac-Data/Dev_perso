"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { DeleteButton } from "@/components/shared/delete-button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PRIORITIES, PRIORITY_BADGE_VARIANT, TASK_STATUSES, humanize } from "@/lib/labels";
import { TaskFormDialog, type TaskValues } from "@/app/(app)/tasks/task-form";
import { deleteTask, setTaskStatus } from "@/app/(app)/tasks/actions";

type Task = {
  id: string;
  title: string;
  description: string | null;
  category: string | null;
  priority: (typeof PRIORITIES)[number];
  status: (typeof TASK_STATUSES)[number];
  deadline: Date | null;
};

export function TaskCard({ task, showStatusSelect = true }: { task: Task; showStatusSelect?: boolean }) {
  const [isPending, startTransition] = useTransition();

  const initialValues: TaskValues = {
    title: task.title,
    description: task.description ?? "",
    category: task.category ?? "",
    priority: task.priority,
    status: task.status,
    deadline: task.deadline ? task.deadline.toISOString().slice(0, 10) : "",
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium">{task.title}</p>
        <div className="flex shrink-0">
          <TaskFormDialog mode="edit" taskId={task.id} initialValues={initialValues} />
          <DeleteButton itemLabel={task.title} action={deleteTask.bind(null, task.id)} />
        </div>
      </div>
      {task.description && <p className="text-xs text-muted-foreground">{task.description}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={PRIORITY_BADGE_VARIANT[task.priority]}>{humanize(task.priority)}</Badge>
        {task.category && <Badge variant="outline">{task.category}</Badge>}
        {task.deadline && (
          <span className="text-xs text-muted-foreground">
            Due {task.deadline.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
          </span>
        )}
      </div>
      {showStatusSelect && (
        <Select
          value={task.status}
          onValueChange={(v) =>
            startTransition(async () => {
              const result = await setTaskStatus(task.id, v as (typeof TASK_STATUSES)[number]);
              if (!result.ok) toast.error(result.error ?? "Could not update");
            })
          }
        >
          <SelectTrigger size="sm" className="w-full" disabled={isPending}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TASK_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

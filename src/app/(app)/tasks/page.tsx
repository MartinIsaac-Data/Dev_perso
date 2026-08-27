import Link from "next/link";
import { ListChecks } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { TASK_STATUSES, humanize } from "@/lib/labels";
import { TaskFormDialog } from "@/app/(app)/tasks/task-form";
import { TaskCard } from "@/app/(app)/tasks/task-card";

const PRIORITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const userId = await requireUserId();
  const { view } = await searchParams;
  const isKanban = view === "kanban";

  const tasks = await prisma.task.findMany({ where: { userId } });
  const sorted = [...tasks].sort((a, b) => {
    const p = (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9);
    if (p !== 0) return p;
    if (a.deadline && b.deadline) return a.deadline.getTime() - b.deadline.getTime();
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return 0;
  });

  return (
    <div>
      <PageHeader
        title="Tasks"
        description="A lightweight task manager tied to your certifications, projects and goals."
        actions={<TaskFormDialog mode="create" />}
      />

      {tasks.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No tasks yet"
          description="Add the next concrete step toward your MBA and career goals."
          action={<TaskFormDialog mode="create" />}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex gap-1.5">
            <Link
              href="/tasks"
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                !isKanban ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent",
              )}
            >
              List
            </Link>
            <Link
              href="/tasks?view=kanban"
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                isKanban ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent",
              )}
            >
              Kanban
            </Link>
          </div>

          {isKanban ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {TASK_STATUSES.map((status) => (
                <div key={status} className="flex flex-col gap-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    {humanize(status)} ({sorted.filter((t) => t.status === status).length})
                  </p>
                  <div className="flex flex-col gap-2">
                    {sorted
                      .filter((t) => t.status === status)
                      .map((t) => (
                        <TaskCard key={t.id} task={t} />
                      ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {sorted.map((t) => (
                <TaskCard key={t.id} task={t} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

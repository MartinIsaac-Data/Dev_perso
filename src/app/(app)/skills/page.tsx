import { Sparkles } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { humanize } from "@/lib/labels";
import { SkillFormDialog } from "@/app/(app)/skills/skill-form";
import { deleteSkill } from "@/app/(app)/skills/actions";

const LEVEL_PCT: Record<string, number> = { BEGINNER: 25, INTERMEDIATE: 50, ADVANCED: 75, EXPERT: 100 };

export default async function SkillsPage() {
  const userId = await requireUserId();
  const skills = await prisma.skill.findMany({
    where: { userId },
    orderBy: [{ category: "asc" }, { name: "asc" }],
  });

  return (
    <div>
      <PageHeader
        title="Skills"
        description="Where you are today versus where you want to be — across technical, business, leadership and language skills."
        actions={<SkillFormDialog mode="create" />}
      />

      {skills.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="No skills tracked yet"
          description="Add the skills you're building toward your MBA and career goals."
          action={<SkillFormDialog mode="create" />}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {skills.map((skill) => (
            <Card key={skill.id}>
              <CardContent className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">{skill.name}</p>
                    <Badge variant="secondary" className="mt-1">
                      {humanize(skill.category)}
                    </Badge>
                  </div>
                  <div className="flex shrink-0">
                    <SkillFormDialog
                      mode="edit"
                      skillId={skill.id}
                      initialValues={{
                        name: skill.name,
                        category: skill.category,
                        currentLevel: skill.currentLevel,
                        targetLevel: skill.targetLevel,
                        notes: skill.notes ?? "",
                      }}
                    />
                    <DeleteButton itemLabel={skill.name} action={deleteSkill.bind(null, skill.id)} />
                  </div>
                </div>
                <div>
                  <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                    <span>{humanize(skill.currentLevel)}</span>
                    <span>Target: {humanize(skill.targetLevel)}</span>
                  </div>
                  <div className="relative">
                    <Progress value={LEVEL_PCT[skill.currentLevel]} />
                    <div
                      className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-foreground"
                      style={{ left: `${LEVEL_PCT[skill.targetLevel]}%` }}
                      title={`Target: ${humanize(skill.targetLevel)}`}
                    />
                  </div>
                </div>
                {skill.notes && <p className="text-xs text-muted-foreground">{skill.notes}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

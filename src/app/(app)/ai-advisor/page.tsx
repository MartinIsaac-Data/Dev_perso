import { AlertTriangle, BookText } from "lucide-react";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { DeleteButton } from "@/components/shared/delete-button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isAIConfigured } from "@/lib/ai/provider";
import { humanize } from "@/lib/labels";
import { AdvisorChat } from "@/app/(app)/ai-advisor/chat";
import { StoryFormDialog } from "@/app/(app)/ai-advisor/story-form";
import { deleteStory } from "@/app/(app)/ai-advisor/story-actions";

type StoredMessage = { role: "user" | "assistant"; content: string; createdAt: string };

export default async function AIAdvisorPage() {
  const userId = await requireUserId();
  const configured = isAIConfigured();

  const [conversation, stories, projects] = await Promise.all([
    prisma.aIConversation.findFirst({ where: { userId }, orderBy: { createdAt: "asc" } }),
    prisma.leadershipStory.findMany({ where: { userId }, orderBy: { createdAt: "desc" } }),
    prisma.project.findMany({ where: { userId }, select: { id: true, name: true } }),
  ]);

  const messages = (conversation?.messages as unknown as StoredMessage[]) ?? [];

  return (
    <div>
      <PageHeader
        title="AI Career Advisor"
        description="A conversational assistant grounded in your own data — it never invents achievements."
      />

      {!configured && (
        <Card className="mb-6 border-warning/40 bg-warning/5">
          <CardContent className="flex items-start gap-3 py-4">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <p className="text-sm text-muted-foreground">
              No AI provider is configured, so the chat below is disabled. Set <code>AI_PROVIDER</code> (
              <code>openai</code> or <code>anthropic</code>) and the matching API key to enable it. The rest
              of the app works fully without it — the Story Bank below is unaffected.
            </p>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="advisor">
        <TabsList>
          <TabsTrigger value="advisor">Advisor</TabsTrigger>
          <TabsTrigger value="stories">Story Bank</TabsTrigger>
        </TabsList>

        <TabsContent value="advisor" className="mt-4">
          {configured ? (
            <AdvisorChat initialMessages={messages} />
          ) : (
            <EmptyState
              title="Advisor disabled"
              description="Configure an AI provider to start a conversation grounded in your data."
            />
          )}
        </TabsContent>

        <TabsContent value="stories" className="mt-4">
          <div className="mb-4 flex justify-end">
            <StoryFormDialog mode="create" projects={projects} />
          </div>
          {stories.length === 0 ? (
            <EmptyState
              icon={BookText}
              title="No stories saved yet"
              description="Turn your projects and leadership experiences into structured STAR-format stories for MBA essays."
              action={<StoryFormDialog mode="create" projects={projects} />}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {stories.map((s) => (
                <Card key={s.id}>
                  <CardContent className="flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold">{s.title}</p>
                      <div className="flex shrink-0">
                        <StoryFormDialog
                          mode="edit"
                          storyId={s.id}
                          projects={projects}
                          initialValues={{
                            title: s.title,
                            situation: s.situation ?? "",
                            task: s.task ?? "",
                            action: s.action ?? "",
                            result: s.result ?? "",
                            reflection: s.reflection ?? "",
                            tags: s.tags,
                            mbaRelevanceScore: s.mbaRelevanceScore?.toString() ?? "",
                            projectId: s.projectId ?? "none",
                          }}
                        />
                        <DeleteButton itemLabel={s.title} action={deleteStory.bind(null, s.id)} />
                      </div>
                    </div>
                    {s.result && <p className="text-sm text-muted-foreground">{s.result}</p>}
                    {s.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {s.tags.map((tag) => (
                          <Badge key={tag} variant="secondary">
                            {humanize(tag)}
                          </Badge>
                        ))}
                      </div>
                    )}
                    {s.mbaRelevanceScore !== null && (
                      <p className="text-xs text-muted-foreground">MBA relevance: {s.mbaRelevanceScore}/100</p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

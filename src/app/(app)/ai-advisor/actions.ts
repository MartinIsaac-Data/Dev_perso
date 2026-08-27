"use server";

import { revalidatePath } from "next/cache";
import type { Prisma } from "@prisma/client";

import { prisma } from "@/lib/db";
import { requireUserId } from "@/lib/session";
import { generateChatCompletion, isAIConfigured, type ChatMessage } from "@/lib/ai/provider";
import { ADVISOR_SYSTEM_PROMPT, buildAdvisorContext } from "@/lib/ai/context";

type StoredMessage = { role: "user" | "assistant"; content: string; createdAt: string };

type ActionResult = { ok: boolean; error?: string; messages?: StoredMessage[] };

export async function sendAdvisorMessage(content: string): Promise<ActionResult> {
  const userId = await requireUserId();

  if (!isAIConfigured()) {
    return { ok: false, error: "No AI provider is configured. Set AI_PROVIDER and an API key to enable the advisor." };
  }
  if (!content.trim()) return { ok: false, error: "Message cannot be empty" };

  let conversation = await prisma.aIConversation.findFirst({ where: { userId }, orderBy: { createdAt: "asc" } });
  if (!conversation) {
    conversation = await prisma.aIConversation.create({ data: { userId, title: "Career advisor" } });
  }

  const existing = (conversation.messages as unknown as StoredMessage[]) ?? [];
  const userMessage: StoredMessage = { role: "user", content, createdAt: new Date().toISOString() };
  const withUser = [...existing, userMessage];

  await prisma.aIConversation.update({
    where: { id: conversation.id },
    data: { messages: withUser as unknown as Prisma.InputJsonValue[] },
  });

  const dataSnapshot = await buildAdvisorContext(userId);
  const system = `${ADVISOR_SYSTEM_PROMPT}\n\n--- USER DATA SNAPSHOT ---\n${dataSnapshot}`;
  const chatHistory: ChatMessage[] = withUser.slice(-12).map((m) => ({ role: m.role, content: m.content }));

  let reply: string;
  try {
    reply = await generateChatCompletion({ system, messages: chatHistory, maxTokens: 800 });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "The AI provider request failed" };
  }

  const assistantMessage: StoredMessage = {
    role: "assistant",
    content: reply || "I couldn't generate a response — please try again.",
    createdAt: new Date().toISOString(),
  };
  const final = [...withUser, assistantMessage];

  await prisma.aIConversation.update({
    where: { id: conversation.id },
    data: { messages: final as unknown as Prisma.InputJsonValue[] },
  });

  revalidatePath("/ai-advisor");
  return { ok: true, messages: final };
}

export async function clearAdvisorConversation(): Promise<ActionResult> {
  const userId = await requireUserId();
  await prisma.aIConversation.deleteMany({ where: { userId } });
  revalidatePath("/ai-advisor");
  return { ok: true, messages: [] };
}

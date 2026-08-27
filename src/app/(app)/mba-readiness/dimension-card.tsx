"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

const TARGET = 80;

export function DimensionCard({
  label,
  score,
  weight,
  factors,
  recommendations,
}: {
  label: string;
  score: number;
  weight: number;
  factors: { label: string; value: string }[];
  recommendations: string[];
}) {
  const [open, setOpen] = useState(false);
  const gap = score - TARGET;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full flex-col gap-2 rounded-lg border p-3 text-left transition-colors hover:bg-accent"
      >
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{label}</span>
          <ChevronRight className="size-3.5 text-muted-foreground" />
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-xl font-semibold tabular-nums">{score}</span>
          <span className={`text-xs font-medium ${gap >= 0 ? "text-success" : "text-muted-foreground"}`}>
            Target {TARGET} · {gap >= 0 ? "+" : ""}
            {gap}
          </span>
        </div>
        <Progress value={score} />
        <span className="text-xs text-muted-foreground">Weight: {weight}%</span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>
              Score {score}/100 · Weight {weight}% · Target {TARGET}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Calculation factors</p>
              <ul className="flex flex-col gap-1.5">
                {factors.map((f) => (
                  <li key={f.label} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{f.label}</span>
                    <Badge variant="outline">{f.value}</Badge>
                  </li>
                ))}
              </ul>
            </div>
            {recommendations.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Recommendations</p>
                <ul className="flex flex-col gap-1.5 text-sm">
                  {recommendations.map((r) => (
                    <li key={r} className="flex gap-2">
                      <span className="text-muted-foreground">•</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

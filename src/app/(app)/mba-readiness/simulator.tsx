"use client";

import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

type Dimension = { key: string; label: string; score: number; weight: number };

export function ReadinessSimulator({
  dimensions,
  currentTotal,
}: {
  dimensions: Dimension[];
  currentTotal: number;
}) {
  const [selectedKey, setSelectedKey] = useState(dimensions[0]?.key ?? "");
  const [hypotheticalScore, setHypotheticalScore] = useState(dimensions[0]?.score ?? 0);

  const selected = dimensions.find((d) => d.key === selectedKey);

  const projectedTotal = useMemo(() => {
    if (!selected) return currentTotal;
    const delta = ((hypotheticalScore - selected.score) * selected.weight) / 100;
    return Math.round(currentTotal + delta);
  }, [selected, hypotheticalScore, currentTotal]);

  const change = projectedTotal - currentTotal;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FlaskConical className="size-4 text-muted-foreground" /> What-If simulator
        </CardTitle>
        <CardDescription>
          A planning tool, not an admission predictor. Try a hypothetical dimension score and see the
          projected effect on your total readiness score.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label>Dimension</Label>
            <Select
              value={selectedKey}
              onValueChange={(key) => {
                setSelectedKey(key);
                const d = dimensions.find((dim) => dim.key === key);
                setHypotheticalScore(d?.score ?? 0);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {dimensions.map((d) => (
                  <SelectItem key={d.key} value={d.key}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Hypothetical score (0-100)</Label>
            <Input
              type="number"
              min={0}
              max={100}
              value={hypotheticalScore}
              onChange={(e) => setHypotheticalScore(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg border p-4">
          <div>
            <p className="text-xs text-muted-foreground">Current</p>
            <p className="text-2xl font-semibold tabular-nums">{currentTotal}</p>
          </div>
          <div className="text-muted-foreground">→</div>
          <div>
            <p className="text-xs text-muted-foreground">Projected</p>
            <p className="text-2xl font-semibold tabular-nums">{projectedTotal}</p>
          </div>
          <Badge variant={change > 0 ? "success" : change < 0 ? "destructive" : "outline"}>
            {change > 0 ? "+" : ""}
            {change} points
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

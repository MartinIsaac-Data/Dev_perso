import { DIMENSION_CALCULATORS } from "@/lib/scoring/dimensions";
import type { DimensionResult, ReadinessBreakdown, ScoringInputs } from "@/lib/scoring/types";

export function computeReadiness(
  inputs: ScoringInputs,
  dimensionConfig: { key: string; label: string; weight: number }[],
): ReadinessBreakdown {
  const dimensions: DimensionResult[] = dimensionConfig.map((cfg) => {
    const calculator = DIMENSION_CALCULATORS[cfg.key];
    const result = calculator
      ? calculator(inputs)
      : { score: 0, factors: [], recommendations: [] };
    const weighted = (result.score * cfg.weight) / 100;
    return {
      key: cfg.key,
      label: cfg.label,
      score: result.score,
      weight: cfg.weight,
      weighted,
      factors: result.factors,
      recommendations: result.recommendations,
    };
  });

  const totalScore = Math.round(dimensions.reduce((sum, d) => sum + d.weighted, 0));

  return { totalScore, dimensions };
}

export type { ScoringInputs, ReadinessBreakdown, DimensionResult } from "@/lib/scoring/types";

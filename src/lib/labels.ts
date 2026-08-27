function toTitleCase(value: string) {
  return value
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function humanize(value: string): string {
  return toTitleCase(value);
}

export const SKILL_CATEGORIES = [
  "TECHNICAL",
  "BUSINESS",
  "LEADERSHIP",
  "DATA",
  "SUPPLY_CHAIN",
  "PROJECT_MANAGEMENT",
  "COMMUNICATION",
  "LANGUAGE",
] as const;

export const SKILL_LEVELS = ["BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"] as const;

export const CERTIFICATION_STATUSES = [
  "NOT_STARTED",
  "PLANNING",
  "IN_PROGRESS",
  "EXAM_SCHEDULED",
  "PASSED",
  "FAILED",
  "EXPIRED",
] as const;

export const EMPLOYMENT_TYPES = [
  "FULL_TIME",
  "PART_TIME",
  "INTERNSHIP",
  "CONTRACT",
  "FREELANCE",
] as const;

export const IMPACT_CATEGORIES = [
  "COST_REDUCTION",
  "REVENUE",
  "PRODUCTIVITY",
  "TIME_SAVED",
  "QUALITY",
  "SERVICE_LEVEL",
  "INVENTORY",
  "FORECAST_ACCURACY",
  "CUSTOMER_SATISFACTION",
  "RISK_REDUCTION",
  "AUTOMATION",
  "DIGITAL_TRANSFORMATION",
] as const;

export const LEADERSHIP_TYPES = [
  "PROJECT_LEADERSHIP",
  "TEAM_LEADERSHIP",
  "MENTORING",
  "TEACHING",
  "COMMUNITY",
  "ENTREPRENEURSHIP",
] as const;

export const INTERNATIONAL_EXPOSURE_TYPES = [
  "WORKED_IN_COUNTRY",
  "MANAGED_STAKEHOLDERS",
  "MANAGED_SUPPLY",
  "INTERNATIONAL_PROJECT",
  "INTERNATIONAL_CLIENT",
  "MULTICULTURAL_TEAM",
  "BUSINESS_TRAVEL",
] as const;

export const EVIDENCE_TYPES = [
  "PDF",
  "IMAGE",
  "EXCEL",
  "POWERPOINT",
  "WORD",
  "CERTIFICATE",
  "EMAIL_SCREENSHOT",
  "KPI_REPORT",
  "MANAGER_FEEDBACK",
  "PERFORMANCE_REVIEW",
  "OTHER",
] as const;

export const CERTIFICATION_STATUS_BADGE_VARIANT: Record<
  (typeof CERTIFICATION_STATUSES)[number],
  "default" | "secondary" | "success" | "warning" | "destructive" | "outline"
> = {
  NOT_STARTED: "outline",
  PLANNING: "secondary",
  IN_PROGRESS: "warning",
  EXAM_SCHEDULED: "warning",
  PASSED: "success",
  FAILED: "destructive",
  EXPIRED: "destructive",
};

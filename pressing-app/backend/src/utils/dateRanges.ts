export type Period = "today" | "week" | "month" | "quarter" | "year" | "custom";

export function resolveDateRange(
  period: string | undefined,
  from?: string,
  to?: string
): { from: Date; to: Date } {
  const now = new Date();
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 59, 999);

  if (period === "custom" && from && to) {
    return { from: new Date(from), to: new Date(to) };
  }

  const start = new Date(now);
  start.setHours(0, 0, 0, 0);

  switch (period) {
    case "week": {
      const day = start.getDay() === 0 ? 7 : start.getDay();
      start.setDate(start.getDate() - (day - 1));
      return { from: start, to: endOfToday };
    }
    case "month":
      start.setDate(1);
      return { from: start, to: endOfToday };
    case "quarter": {
      const quarterStartMonth = Math.floor(start.getMonth() / 3) * 3;
      start.setMonth(quarterStartMonth, 1);
      return { from: start, to: endOfToday };
    }
    case "year":
      start.setMonth(0, 1);
      return { from: start, to: endOfToday };
    case "today":
    default:
      return { from: start, to: endOfToday };
  }
}

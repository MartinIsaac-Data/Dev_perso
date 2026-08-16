/** e.g. PR-20260816-0F3A — date-prefixed so tickets sort and scan naturally. */
export function generateOrderNumber(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const random = Math.random().toString(16).slice(2, 6).toUpperCase();
  return `PR-${y}${m}${d}-${random}`;
}

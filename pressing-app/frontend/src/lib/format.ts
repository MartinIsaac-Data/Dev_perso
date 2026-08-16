export function formatMoney(value: string | number | null | undefined, currency = "FCFA"): string {
  const n = Number(value ?? 0);
  return `${n.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} ${currency}`;
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

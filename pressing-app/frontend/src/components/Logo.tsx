import { cn } from "@/lib/cn";

/**
 * The NMI Clean mark: an N built from two bars and a diagonal, with one
 * corner cut and re-filled in brass — a garment corner folding back into
 * shape. `currentColor` carries the body so it adapts to whatever
 * text/foreground color the parent sets; the fold stays brass everywhere,
 * since it's the one accent used consistently across the identity.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" fill="none" className={className} aria-hidden="true">
      <rect x="18" y="20" width="18" height="60" rx="6" fill="currentColor" />
      <rect x="64" y="20" width="18" height="60" rx="6" fill="currentColor" />
      <polygon points="36,24 50,20 82,64 82,80 68,76 36,36" fill="currentColor" />
      <polygon points="64,20 82,20 82,38" fill="hsl(var(--brass))" />
    </svg>
  );
}

const TILE_SIZE = { sm: "h-7 w-7 rounded-lg", md: "h-9 w-9 rounded-xl", lg: "h-12 w-12 rounded-xl" };
const MARK_SIZE = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-7 w-7" };
const TEXT_SIZE = { sm: "text-sm", md: "text-base", lg: "text-xl" };

export function Logo({
  size = "md",
  withWordmark = true,
  className,
}: {
  size?: "sm" | "md" | "lg";
  withWordmark?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className={cn(TILE_SIZE[size], "flex shrink-0 items-center justify-center bg-primary text-primary-foreground")}>
        <LogoMark className={MARK_SIZE[size]} />
      </div>
      {withWordmark && (
        <span className={cn(TEXT_SIZE[size], "font-display font-medium tracking-tight text-foreground")}>
          NMI <span className="font-semibold">Clean</span>
        </span>
      )}
    </div>
  );
}

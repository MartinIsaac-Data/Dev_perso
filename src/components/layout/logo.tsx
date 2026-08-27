import { Compass } from "lucide-react";

export function Logo({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2 px-3 py-4">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Compass className="size-4.5" />
      </div>
      {!collapsed && (
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">MBA Compass</div>
          <div className="text-[11px] text-muted-foreground">Build the career that gets you there.</div>
        </div>
      )}
    </div>
  );
}

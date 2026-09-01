import { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Tables can carry more columns than fit on a phone even after the
 * lowest-priority ones are hidden (see `hidden md:table-cell` usage across
 * the app). Rather than leave "swipe to see more" undiscoverable, this
 * tracks the scroller's actual scroll position and shows a fade + tap
 * target on whichever edge still has content — both vanish once nothing's
 * left to reveal in that direction, including on desktop where nothing
 * ever overflows.
 */
export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const table = tableRef.current;
    if (!scroller || !table) return;

    function update() {
      const el = scrollerRef.current;
      if (!el) return;
      setCanScrollLeft(el.scrollLeft > 4);
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    }

    update();
    scroller.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(table);
    window.addEventListener("resize", update);
    return () => {
      scroller.removeEventListener("scroll", update);
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  function nudge(delta: number) {
    scrollerRef.current?.scrollBy({ left: delta, behavior: "smooth" });
  }

  return (
    <div className="relative">
      <div ref={scrollerRef} className="w-full overflow-x-auto rounded-lg border border-border">
        <table ref={tableRef} className={cn("w-full caption-bottom text-sm", className)} {...props} />
      </div>
      {canScrollLeft && (
        <>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-8 rounded-l-lg bg-gradient-to-r from-card to-transparent" />
          <button
            type="button"
            aria-label="Voir les colonnes précédentes"
            onClick={() => nudge(-140)}
            className="absolute left-1.5 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
        </>
      )}
      {canScrollRight && (
        <>
          <div className="pointer-events-none absolute inset-y-0 right-0 w-8 rounded-r-lg bg-gradient-to-l from-card to-transparent" />
          <button
            type="button"
            aria-label="Voir plus de colonnes"
            onClick={() => nudge(140)}
            className="absolute right-1.5 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </>
      )}
    </div>
  );
}

export function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("bg-muted/60", className)} {...props} />;
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...props} />;
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-muted/40", className)} {...props} />;
}

export function TableHead({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn("h-10 whitespace-nowrap px-3 text-left text-xs font-medium text-muted-foreground", className)}
      {...props}
    />
  );
}

export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("whitespace-nowrap px-3 py-2.5", className)} {...props} />;
}

import Link from "next/link";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-muted/30 px-4 text-center">
      <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Compass className="size-5" />
      </div>
      <div>
        <p className="text-lg font-semibold">Page not found</p>
        <p className="mt-1 text-sm text-muted-foreground">
          This page doesn&apos;t exist, or you don&apos;t have access to it.
        </p>
      </div>
      <Button asChild size="sm">
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}

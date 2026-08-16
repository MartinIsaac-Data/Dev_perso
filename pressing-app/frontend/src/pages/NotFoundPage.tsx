import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3">
      <p className="text-4xl font-bold">404</p>
      <p className="text-muted-foreground">Page introuvable</p>
      <Link to="/">
        <Button>Retour au dashboard</Button>
      </Link>
    </div>
  );
}

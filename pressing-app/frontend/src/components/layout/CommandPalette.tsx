import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { Search, ShoppingBag, User } from "lucide-react";
import { api } from "@/lib/api";

interface Results {
  customers: { id: string; fullName: string; phone: string }[];
  orders: { id: string; orderNumber: string; status: string; customer: { fullName: string } }[];
  articles: { id: string; articleType: string; orderId: string; order: { orderNumber: string } }[];
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>({ customers: [], orders: [], articles: [] });
  const navigate = useNavigate();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setResults({ customers: [], orders: [], articles: [] });
      return;
    }
    const timeout = setTimeout(() => {
      api.get("/search", { params: { q: query } }).then((res) => setResults(res.data));
    }, 200);
    return () => clearTimeout(timeout);
  }, [query, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-24" onClick={() => setOpen(false)}>
      <Command
        className="w-full max-w-lg overflow-hidden rounded-lg border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
        shouldFilter={false}
      >
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="h-4 w-4 text-muted-foreground" />
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder="Rechercher un client, une commande, un article..."
            className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
            {query.length < 2 ? "Tapez au moins 2 caractères" : "Aucun résultat"}
          </Command.Empty>

          {results.customers.length > 0 && (
            <Command.Group heading="Clients" className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {results.customers.map((c) => (
                <Command.Item
                  key={c.id}
                  onSelect={() => {
                    navigate(`/customers/${c.id}`);
                    setOpen(false);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent"
                >
                  <User className="h-4 w-4" /> {c.fullName} — {c.phone}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {results.orders.length > 0 && (
            <Command.Group heading="Commandes" className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {results.orders.map((o) => (
                <Command.Item
                  key={o.id}
                  onSelect={() => {
                    navigate(`/orders/${o.id}`);
                    setOpen(false);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent"
                >
                  <ShoppingBag className="h-4 w-4" /> {o.orderNumber} — {o.customer.fullName} ({o.status})
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {results.articles.length > 0 && (
            <Command.Group heading="Articles" className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {results.articles.map((a) => (
                <Command.Item
                  key={a.id}
                  onSelect={() => {
                    navigate(`/orders/${a.orderId}`);
                    setOpen(false);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent"
                >
                  {a.articleType} — commande {a.order.orderNumber}
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}

import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, TableSkeleton } from "@/components/ui/states";
import { useAuth } from "@/contexts/AuthContext";

const CATEGORIES = [
  ["DETERGENT", "Lessive"],
  ["SOFTENER", "Adoucissant"],
  ["STAIN_REMOVER", "Détachant"],
  ["BLEACH", "Eau de Javel"],
  ["PACKAGING", "Emballages"],
  ["BAGS", "Sacs"],
  ["HANGERS", "Cintres"],
  ["LABELS", "Étiquettes"],
  ["OTHER", "Autres"],
];

interface Product {
  id: string;
  name: string;
  category: string;
  currentStock: string | number;
  minStock: string | number;
  unit: string;
  supplier?: string | null;
}

export default function InventoryPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [movementProduct, setMovementProduct] = useState<Product | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: async () => (await api.get<Product[]>("/inventory")).data,
  });

  const lowStockCount = data?.filter((p) => Number(p.currentStock) <= Number(p.minStock)).length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Stock</h1>
          {lowStockCount > 0 && (
            <p className="flex items-center gap-1 text-sm text-warning">
              <AlertTriangle className="h-4 w-4" /> {lowStockCount} produit(s) sous le seuil minimum
            </p>
          )}
        </div>
        {hasPermission("inventory:write") && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Nouveau produit
          </Button>
        )}
      </div>

      <Card>
        {isLoading ? (
          <TableSkeleton />
        ) : !data?.length ? (
          <EmptyState title="Aucun produit en stock" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Produit</TableHead>
                <TableHead className="hidden md:table-cell">Catégorie</TableHead>
                <TableHead>Stock actuel</TableHead>
                <TableHead className="hidden lg:table-cell">Stock minimum</TableHead>
                <TableHead className="hidden lg:table-cell">Fournisseur</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => {
                const low = Number(p.currentStock) <= Number(p.minStock);
                return (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      {CATEGORIES.find(([k]) => k === p.category)?.[1] ?? p.category}
                    </TableCell>
                    <TableCell>
                      {p.currentStock} {p.unit}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {p.minStock} {p.unit}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">{p.supplier ?? "—"}</TableCell>
                    <TableCell>
                      <Badge tone={low ? "warning" : "success"}>{low ? "Stock bas" : "OK"}</Badge>
                    </TableCell>
                    <TableCell>
                      {hasPermission("inventory:write") && (
                        <Button size="sm" variant="outline" onClick={() => setMovementProduct(p)}>
                          Mouvement
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <CreateProductDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["products"] })}
      />
      {movementProduct && (
        <MovementDialog
          product={movementProduct}
          onClose={() => setMovementProduct(null)}
          onDone={() => queryClient.invalidateQueries({ queryKey: ["products"] })}
        />
      )}
    </div>
  );
}

function CreateProductDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/inventory", {
        name: form.get("name"),
        category: form.get("category"),
        currentStock: Number(form.get("currentStock")) || 0,
        minStock: Number(form.get("minStock")) || 0,
        unit: form.get("unit"),
        supplier: form.get("supplier") || undefined,
      });
      toast.success("Produit ajouté");
      onCreated();
      onClose();
      e.currentTarget.reset();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Nouveau produit">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="name">Nom *</Label>
          <Input id="name" name="name" required />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="category">Catégorie *</Label>
            <Select id="category" name="category" required>
              {CATEGORIES.map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="unit">Unité *</Label>
            <Input id="unit" name="unit" placeholder="bidon, unité..." required />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="currentStock">Stock initial</Label>
            <Input id="currentStock" name="currentStock" type="number" min={0} defaultValue={0} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="minStock">Stock minimum</Label>
            <Input id="minStock" name="minStock" type="number" min={0} defaultValue={0} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="supplier">Fournisseur</Label>
          <Input id="supplier" name="supplier" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Ajout..." : "Ajouter"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function MovementDialog({ product, onClose, onDone }: { product: Product; onClose: () => void; onDone: () => void }) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const form = new FormData(e.currentTarget);
    try {
      await api.post(`/inventory/${product.id}/transactions`, {
        type: form.get("type"),
        quantity: Number(form.get("quantity")),
        reason: form.get("reason") || undefined,
      });
      toast.success("Mouvement enregistré");
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={`Mouvement de stock — ${product.name}`}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Stock actuel : {product.currentStock} {product.unit}
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="type">Type</Label>
            <Select id="type" name="type" defaultValue="ENTRY">
              <option value="ENTRY">Entrée</option>
              <option value="EXIT">Sortie</option>
              <option value="ADJUSTMENT">Ajustement</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="quantity">Quantité</Label>
            <Input id="quantity" name="quantity" type="number" required />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="reason">Motif</Label>
          <Input id="reason" name="reason" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Enregistrement..." : "Valider"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

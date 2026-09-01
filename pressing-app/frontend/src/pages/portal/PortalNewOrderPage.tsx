import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { apiErrorMessage } from "@/lib/api";
import { usePortalAuth } from "@/contexts/PortalAuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMoney } from "@/lib/format";
import { ARTICLE_CATEGORY_LABELS } from "@/lib/statusMeta";
import type { Service } from "@/types";

interface DraftItem {
  key: string;
  category: string;
  articleType: string;
  quantity: number;
  serviceId: string;
  isExpress: boolean;
}

export default function PortalNewOrderPage() {
  const navigate = useNavigate();
  const { customer } = usePortalAuth();
  const [items, setItems] = useState<DraftItem[]>([]);
  const [fulfillment, setFulfillment] = useState<"PICKUP" | "DELIVERY">("PICKUP");
  const [deliveryAddress, setDeliveryAddress] = useState(customer?.address ?? "");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { data: services } = useQuery({
    queryKey: ["portal-services"],
    queryFn: async () => (await portalApi.get<Service[]>("/portal/services")).data,
  });

  function addItem() {
    setItems((prev) => [
      ...prev,
      { key: crypto.randomUUID(), category: "SHIRT", articleType: "", quantity: 1, serviceId: services?.[0]?.id ?? "", isExpress: false },
    ]);
  }
  function updateItem(key: string, patch: Partial<DraftItem>) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)));
  }
  function removeItem(key: string) {
    setItems((prev) => prev.filter((it) => it.key !== key));
  }

  function priceForItem(item: DraftItem): number {
    const service = services?.find((s) => s.id === item.serviceId);
    if (!service) return 0;
    const unit = item.isExpress && service.expressPrice ? Number(service.expressPrice) : Number(service.price);
    return unit * item.quantity;
  }

  const subtotal = items.reduce((sum, item) => sum + priceForItem(item), 0);
  const deliveryFee = fulfillment === "DELIVERY" ? 1000 : 0;
  const total = subtotal + deliveryFee;

  async function handleSubmit() {
    if (items.length === 0) return toast.error("Ajoutez au moins un article");
    if (items.some((it) => !it.articleType || !it.serviceId)) {
      return toast.error("Complétez le type d'article et le service pour chaque ligne");
    }
    if (fulfillment === "DELIVERY" && !deliveryAddress) {
      return toast.error("Indiquez une adresse de livraison");
    }

    setSubmitting(true);
    try {
      const res = await portalApi.post("/portal/orders", {
        priority: "NORMAL",
        notes: notes || undefined,
        fulfillment,
        deliveryAddress: fulfillment === "DELIVERY" ? deliveryAddress : undefined,
        items: items.map((it) => ({
          category: it.category,
          articleType: it.articleType,
          quantity: it.quantity,
          serviceId: it.serviceId,
          isExpress: it.isExpress,
        })),
      });
      toast.success(`Réservation ${res.data.orderNumber} envoyée`);
      navigate(`/portal/orders/${res.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Impossible d'envoyer la réservation"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4 pb-32 sm:pb-24">
      <div>
        <h1 className="text-2xl font-semibold">Nouvelle réservation</h1>
        <p className="text-sm text-muted-foreground">Choisissez vos articles, le pressing s'occupe du reste.</p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Articles</CardTitle>
          <Button size="sm" variant="outline" onClick={addItem}>
            <Plus className="h-4 w-4" /> Ajouter un article
          </Button>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun article ajouté.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Catégorie</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Qté</TableHead>
                  <TableHead>Service</TableHead>
                  <TableHead>Express</TableHead>
                  <TableHead>Prix</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.key}>
                    <TableCell>
                      <Select value={item.category} onChange={(e) => updateItem(item.key, { category: e.target.value })} className="w-36">
                        {Object.entries(ARTICLE_CATEGORY_LABELS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Input
                        placeholder="ex: Chemise blanche"
                        value={item.articleType}
                        onChange={(e) => updateItem(item.key, { articleType: e.target.value })}
                        className="w-40"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        value={item.quantity}
                        onChange={(e) => updateItem(item.key, { quantity: Number(e.target.value) || 1 })}
                        className="w-16"
                      />
                    </TableCell>
                    <TableCell>
                      <Select value={item.serviceId} onChange={(e) => updateItem(item.key, { serviceId: e.target.value })} className="w-48">
                        {services?.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name} ({formatMoney(s.price)})
                          </option>
                        ))}
                      </Select>
                    </TableCell>
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={item.isExpress}
                        onChange={(e) => updateItem(item.key, { isExpress: e.target.checked })}
                        className="h-4 w-4"
                      />
                    </TableCell>
                    <TableCell className="font-medium">{formatMoney(priceForItem(item))}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" onClick={() => removeItem(item.key)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retrait ou livraison</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Button variant={fulfillment === "PICKUP" ? "default" : "outline"} onClick={() => setFulfillment("PICKUP")}>
              Je dépose / récupère en boutique
            </Button>
            <Button variant={fulfillment === "DELIVERY" ? "default" : "outline"} onClick={() => setFulfillment("DELIVERY")}>
              Livraison (+{formatMoney(1000)})
            </Button>
          </div>
          {fulfillment === "DELIVERY" && (
            <div className="space-y-1.5">
              <Label htmlFor="deliveryAddress">Adresse de livraison</Label>
              <Input id="deliveryAddress" value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} required />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="notes">Remarques (facultatif)</Label>
            <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-lg font-semibold">Total estimé : {formatMoney(total)}</p>
          <Button size="lg" className="w-full sm:w-auto" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Envoi..." : "Envoyer ma réservation"}
          </Button>
        </div>
      </div>
    </div>
  );
}

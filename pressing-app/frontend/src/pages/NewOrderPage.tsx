import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2, Search } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMoney } from "@/lib/format";
import { ARTICLE_CATEGORY_LABELS } from "@/lib/statusMeta";
import type { Customer, Paginated, Service } from "@/types";

interface DraftItem {
  key: string;
  category: string;
  articleType: string;
  quantity: number;
  serviceId: string;
  isExpress: boolean;
  color?: string;
}

export default function NewOrderPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedCustomerId = searchParams.get("customerId") ?? "";

  const [customerId, setCustomerId] = useState(preselectedCustomerId);
  const [customerSearch, setCustomerSearch] = useState("");
  const [priority, setPriority] = useState<"NORMAL" | "EXPRESS">("NORMAL");
  const [discount, setDiscount] = useState(0);
  const [deliveryFee, setDeliveryFee] = useState(0);
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [payNow, setPayNow] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [submitting, setSubmitting] = useState(false);

  const { data: customers } = useQuery({
    queryKey: ["customers-all"],
    queryFn: async () => (await api.get<Paginated<Customer>>("/customers", { params: { pageSize: 100 } })).data.data,
  });
  const { data: services } = useQuery({
    queryKey: ["services-active"],
    queryFn: async () => (await api.get<Service[]>("/services", { params: { activeOnly: "true" } })).data,
  });

  const filteredCustomers = useMemo(() => {
    if (!customers) return [];
    if (!customerSearch) return customers.slice(0, 8);
    const q = customerSearch.toLowerCase();
    return customers.filter((c) => c.fullName.toLowerCase().includes(q) || c.phone.includes(q)).slice(0, 8);
  }, [customers, customerSearch]);

  const selectedCustomer = customers?.find((c) => c.id === customerId);

  function addItem() {
    setItems((prev) => [
      ...prev,
      {
        key: crypto.randomUUID(),
        category: "SHIRT",
        articleType: "",
        quantity: 1,
        serviceId: services?.[0]?.id ?? "",
        isExpress: priority === "EXPRESS",
      },
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
  const total = Math.max(0, subtotal + Number(deliveryFee || 0) - Number(discount || 0));

  async function handleSubmit() {
    if (!customerId) return toast.error("Sélectionnez un client");
    if (items.length === 0) return toast.error("Ajoutez au moins un article");
    if (items.some((it) => !it.articleType || !it.serviceId)) {
      return toast.error("Complétez le type d'article et le service pour chaque ligne");
    }

    setSubmitting(true);
    try {
      const res = await api.post("/orders", {
        customerId,
        priority,
        discount: Number(discount) || 0,
        deliveryFee: Number(deliveryFee) || 0,
        notes: notes || undefined,
        items: items.map((it) => ({
          category: it.category,
          articleType: it.articleType,
          quantity: it.quantity,
          serviceId: it.serviceId,
          isExpress: it.isExpress,
          color: it.color || undefined,
        })),
        initialPayment: payNow && paymentAmount > 0 ? { amount: Number(paymentAmount), method: paymentMethod } : undefined,
      });
      toast.success(`Commande ${res.data.orderNumber} créée`);
      navigate(`/orders/${res.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Impossible de créer la commande"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4 pb-36 sm:pb-24">
      <div>
        <h1 className="text-2xl font-semibold">Nouvelle commande</h1>
        <p className="text-sm text-muted-foreground">Client → articles → services → paiement</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Client</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {selectedCustomer ? (
            <div className="flex items-center justify-between rounded-md border border-border p-2.5">
              <div>
                <p className="font-medium">{selectedCustomer.fullName}</p>
                <p className="text-sm text-muted-foreground">{selectedCustomer.phone}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setCustomerId("")}>
                Changer
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  autoFocus
                  placeholder="Rechercher un client par nom ou téléphone..."
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                  className="pl-8"
                />
              </div>
              <div className="max-h-64 overflow-y-auto rounded-md border border-border">
                {filteredCustomers.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setCustomerId(c.id)}
                    className="flex w-full items-center justify-between gap-3 border-b border-border px-3 py-2 text-left text-sm last:border-b-0 hover:bg-accent"
                  >
                    <div>
                      <p className="font-medium">{c.fullName}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.phone}
                        {c.email ? ` • ${c.email}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {c._count?.orders ?? 0} commande{(c._count?.orders ?? 0) === 1 ? "" : "s"}
                    </span>
                  </button>
                ))}
                {filteredCustomers.length === 0 && (
                  <p className="p-3 text-sm text-muted-foreground">Aucun client trouvé.</p>
                )}
              </div>
              {customerSearch && filteredCustomers.length > 1 && (
                <p className="text-xs text-muted-foreground">
                  {filteredCustomers.length} clients correspondent — vérifiez le téléphone avant de choisir.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>2. Articles</CardTitle>
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
                      <Select
                        value={item.category}
                        onChange={(e) => updateItem(item.key, { category: e.target.value })}
                        className="w-36"
                      >
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
                      <Select
                        value={item.serviceId}
                        onChange={(e) => updateItem(item.key, { serviceId: e.target.value })}
                        className="w-48"
                      >
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
          <CardTitle>3. Priorité, remise et livraison</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Priorité</Label>
            <Select value={priority} onChange={(e) => setPriority(e.target.value as "NORMAL" | "EXPRESS")}>
              <option value="NORMAL">Normale</option>
              <option value="EXPRESS">Express</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Remise (FCFA)</Label>
            <Input type="number" min={0} value={discount} onChange={(e) => setDiscount(Number(e.target.value))} />
          </div>
          <div className="space-y-1.5">
            <Label>Frais de livraison (FCFA)</Label>
            <Input type="number" min={0} value={deliveryFee} onChange={(e) => setDeliveryFee(Number(e.target.value))} />
          </div>
          <div className="col-span-2 space-y-1.5 sm:col-span-4">
            <Label>Notes</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>4. Paiement</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={payNow} onChange={(e) => setPayNow(e.target.checked)} className="h-4 w-4" />
            Le client paie maintenant
          </label>
          {payNow && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Montant</Label>
                <Input
                  type="number"
                  min={0}
                  max={total}
                  value={paymentAmount}
                  onChange={(e) => setPaymentAmount(Number(e.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Moyen de paiement</Label>
                <Select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
                  <option value="CASH">Cash</option>
                  <option value="ORANGE_MONEY">Orange Money</option>
                  <option value="MTN_MOMO">MTN Mobile Money</option>
                  <option value="CARD">Carte</option>
                  <option value="BANK_TRANSFER">Virement</option>
                  <option value="OTHER">Autre</option>
                </Select>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm">
            <p className="text-muted-foreground">
              Sous-total {formatMoney(subtotal)} {deliveryFee ? `+ livraison ${formatMoney(deliveryFee)}` : ""}{" "}
              {discount ? `− remise ${formatMoney(discount)}` : ""}
            </p>
            <p className="text-lg font-semibold">Total : {formatMoney(total)}</p>
          </div>
          <Button size="lg" className="w-full sm:w-auto" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Création..." : "Créer la commande"}
          </Button>
        </div>
      </div>
    </div>
  );
}

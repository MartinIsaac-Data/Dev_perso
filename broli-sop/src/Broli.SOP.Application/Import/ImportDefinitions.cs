namespace Broli.SOP.Application.Import;

public enum CellKind { Text, Number, Date, Month, Integer }

public record ColumnDef(string Name, CellKind Kind, bool Required, params string[] Aliases);

public record ImportDefinition(
    ImportType Type,
    string Slug,
    string Title,
    string Description,
    IReadOnlyList<ColumnDef> Columns,
    IReadOnlyList<object?[]> Example)
{
    public IEnumerable<ColumnDef> RequiredColumns => Columns.Where(c => c.Required);
    public IEnumerable<ColumnDef> OptionalColumns => Columns.Where(c => !c.Required);
}

/// <summary>The standard Excel templates. Column names are matched case/space/accent-insensitively, with aliases.</summary>
public static class ImportDefinitions
{
    public static readonly IReadOnlyList<ImportDefinition> All =
    [
        new(ImportType.SupplierMaster, "supplier-master", "SUPPLIER MASTER",
            "Suppliers and their origin country. Import before PRODUCT MASTER and SUPPLY.",
            [
                new("Supplier Code", CellKind.Text, true, "code", "supplier id", "code fournisseur"),
                new("Supplier Name", CellKind.Text, true, "name", "supplier", "fournisseur", "nom"),
                new("Country", CellKind.Text, true, "pays", "origin", "country code"),
                new("Transit Days", CellKind.Integer, false, "transit time", "transit"),
                new("Production Lead Days", CellKind.Integer, false, "lead time", "production lead time"),
            ],
            [["SUP-001", "Anatolia Films Ltd", "TR", 30, 20]]),

        new(ImportType.ProductMaster, "product-master", "PRODUCT MASTER",
            "Articles (CArtSAP). The first real master import removes all DEMO data.",
            [
                new("CArtSAP", CellKind.Text, true, "cart sap", "code article", "article", "sku", "material code"),
                new("Description", CellKind.Text, true, "designation", "libelle", "product"),
                new("Category", CellKind.Text, true, "family", "product family", "famille", "categorie"),
                new("Brand", CellKind.Text, false, "marque"),
                new("Unit Weight", CellKind.Number, false, "unit weight kg", "poids unitaire", "weight"),
                new("Colisage", CellKind.Number, false, "units per carton", "pcb"),
                new("TC Conversion", CellKind.Number, false, "qty per tc", "units per tc", "tc"),
                new("Material Type", CellKind.Text, false, "type", "material", "type article"),
                new("Unit", CellKind.Text, false, "base unit", "uom", "unite"),
                new("Unit Cost", CellKind.Number, false, "cost", "standard cost", "cout"),
                new("Safety Stock", CellKind.Number, false, "stock securite", "ss"),
                new("Main Supplier", CellKind.Text, false, "supplier", "supplier code", "fournisseur"),
                new("Format", CellKind.Text, false),
                new("Color", CellKind.Text, false, "colour", "couleur"),
            ],
            [["100245", "SPAGHETTI RAHMA 500G", "SPAGHETTI", "Rahma", 0.5, 20, 2400, "Finished Good", "CTN", 8500, null, null, "500g", null]]),

        new(ImportType.Sales, "sales", "FACT_SALES",
            "Monthly demand per product and agency: forecast, actual and (optionally) ordered quantities.",
            [
                new("Date", CellKind.Month, true, "month", "period", "mois"),
                new("CArtSAP", CellKind.Text, true, "cart sap", "code article", "article", "sku"),
                new("Product", CellKind.Text, false, "description", "designation"),
                new("Brand", CellKind.Text, false, "marque"),
                new("Agency", CellKind.Text, true, "agence", "branch"),
                new("Forecast", CellKind.Number, true, "prevision", "fcst"),
                new("Actual", CellKind.Number, true, "sales", "ventes", "realise", "actual qty"),
                new("Ordered", CellKind.Number, false, "orders", "commandes", "ordered qty"),
            ],
            [[new DateTime(2026, 9, 1), "100245", "SPAGHETTI RAHMA 500G", "Rahma", "Douala", 1200, 1130, 1180]]),

        new(ImportType.Inventory, "inventory", "INVENTORY",
            "Stock snapshot per product and warehouse (month-end recommended).",
            [
                new("Date", CellKind.Date, true, "snapshot date", "date stock"),
                new("CArtSAP", CellKind.Text, true, "cart sap", "code article", "article", "sku"),
                new("Product", CellKind.Text, false, "description", "designation"),
                new("Stock", CellKind.Number, true, "quantity", "qty", "stock qty", "quantite"),
                new("Warehouse", CellKind.Text, true, "entrepot", "magasin", "location"),
            ],
            [[new DateTime(2026, 9, 30), "100245", "SPAGHETTI RAHMA 500G", 5400, "Douala Central"]]),

        new(ImportType.Supply, "supply", "SUPPLY",
            "Purchase-order lines and shipment tracking. Key: PO + CArtSAP.",
            [
                new("PO", CellKind.Text, true, "po number", "purchase order", "commande", "bon de commande"),
                new("CArtSAP", CellKind.Text, true, "cart sap", "code article", "article", "sku"),
                new("Product", CellKind.Text, false, "description", "designation"),
                new("Supplier", CellKind.Text, true, "supplier code", "fournisseur"),
                new("Quantity", CellKind.Number, true, "qty", "quantite"),
                new("Country", CellKind.Text, false, "origin", "pays"),
                new("ETD", CellKind.Date, false, "departure"),
                new("ETA", CellKind.Date, false, "arrival", "estimated arrival"),
                new("Status", CellKind.Text, true, "statut"),
                new("Order Date", CellKind.Date, false, "po date", "date commande"),
                new("Required Date", CellKind.Date, false, "need date", "date besoin"),
                new("Actual Arrival", CellKind.Date, false, "arrival date", "date arrivee"),
                new("Delivered Qty", CellKind.Number, false, "received qty", "qte recue"),
                new("TC", CellKind.Number, false, "containers", "conteneurs"),
                new("Port", CellKind.Text, false),
                new("Booking", CellKind.Text, false),
                new("BL", CellKind.Text, false, "bill of lading"),
                new("Customs Status", CellKind.Text, false, "customs", "douane"),
            ],
            [["4500123456", "300101", "FILM RAHMA SPAGHETTI 500G", "SUP-001", 25000, "TR",
              new DateTime(2026, 9, 5), new DateTime(2026, 10, 8), "Shipped", new DateTime(2026, 8, 10), new DateTime(2026, 10, 10), null, null, 1, "Douala", "BK12345", "MEDU1234567", null]]),

        new(ImportType.Forecast, "forecast", "FORECAST",
            "Forward forecast per product and month. Replaces the forecast for the months supplied.",
            [
                new("CArtSAP", CellKind.Text, true, "cart sap", "code article", "article", "sku"),
                new("Month", CellKind.Month, true, "date", "period", "mois"),
                new("Forecast", CellKind.Number, true, "prevision", "qty", "fcst"),
            ],
            [["100245", new DateTime(2026, 10, 1), 1250]]),
    ];

    public static ImportDefinition? Find(string slugOrType) =>
        All.FirstOrDefault(d => string.Equals(d.Slug, slugOrType, StringComparison.OrdinalIgnoreCase)
                                || string.Equals(d.Type.ToString(), slugOrType, StringComparison.OrdinalIgnoreCase));

    public static ImportDefinition Get(ImportType type) => All.First(d => d.Type == type);
}

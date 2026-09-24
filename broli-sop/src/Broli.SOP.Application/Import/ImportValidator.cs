namespace Broli.SOP.Application.Import;

public record ValidationOutcome(
    IReadOnlyList<ImportIssue> Issues,
    IReadOnlyList<object> ValidRows,
    int RowCount,
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyDictionary<string, string?>> Samples)
{
    public int ErrorCount => Issues.Count(i => i.Severity == "Error");
    public int WarningCount => Issues.Count(i => i.Severity == "Warning");
}

/// <summary>
/// Validates a raw sheet against a template: missing columns, blanks, formats, invalid dates,
/// negative values, duplicates and unknown business keys. Any error blocks the whole import.
/// </summary>
public static class ImportValidator
{
    public const int MaxIssues = 1000;

    public static ValidationOutcome Validate(ImportDefinition def, RawSheet sheet, ImportLookups lookups)
    {
        var issues = new List<ImportIssue>();
        var rows = new List<object>();

        // Map template columns to sheet columns.
        var index = new Dictionary<string, int>();
        var normalizedHeaders = sheet.Headers.Select(CellParser.Normalize).ToList();
        foreach (var col in def.Columns)
        {
            var names = new[] { col.Name }.Concat(col.Aliases).Select(CellParser.Normalize).ToHashSet();
            var i = normalizedHeaders.FindIndex(h => names.Contains(h));
            if (i >= 0) index[col.Name] = i;
            else if (col.Required) issues.Add(new ImportIssue(0, col.Name, $"Colonne obligatoire manquante : « {col.Name} ».", "Error"));
        }

        var samples = sheet.Rows.Take(20).Select(r =>
            (IReadOnlyDictionary<string, string?>)sheet.Headers.Select((h, i) => (h, v: i < r.Cells.Count ? CellParser.Text(r.Cells[i]) : null))
                .GroupBy(x => x.h).ToDictionary(g => g.Key, g => g.First().v)).ToList();

        if (issues.Count > 0) return new ValidationOutcome(issues, rows, sheet.Rows.Count, sheet.Headers, samples);
        if (sheet.Rows.Count == 0)
        {
            issues.Add(new ImportIssue(0, null, "La feuille ne contient aucune ligne de données.", "Error"));
            return new ValidationOutcome(issues, rows, 0, sheet.Headers, samples);
        }

        var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var newCategories = new Dictionary<string, MaterialType?>(StringComparer.OrdinalIgnoreCase);
        var newAgencies = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var newWarehouses = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var fileProducts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var raw in sheet.Rows)
        {
            if (issues.Count >= MaxIssues) break;
            var ctx = new RowContext(def, raw, index, issues);

            object? row = def.Type switch
            {
                ImportType.SupplierMaster => SupplierRow(ctx, lookups),
                ImportType.ProductMaster => ProductRow(ctx, lookups, newCategories, fileProducts),
                ImportType.Sales => SalesRow(ctx, lookups, newAgencies),
                ImportType.Inventory => InventoryRow(ctx, lookups, newWarehouses),
                ImportType.Supply => SupplyRow(ctx, lookups),
                ImportType.Forecast => ForecastRow(ctx, lookups),
                _ => null,
            };
            if (row is null || ctx.HasError) continue;

            var key = Key(row);
            if (seen.TryGetValue(key, out var firstRow))
            {
                issues.Add(new ImportIssue(raw.ExcelRow, null, $"Doublon de la ligne {firstRow} (même clé : {key}).", "Error"));
                continue;
            }
            seen[key] = raw.ExcelRow;
            rows.Add(row);
        }

        foreach (var (code, _) in newCategories)
            issues.Add(new ImportIssue(0, "Category", $"La nouvelle catégorie « {code} » sera créée.", "Warning"));
        foreach (var a in newAgencies)
            issues.Add(new ImportIssue(0, "Agency", $"La nouvelle agence « {a} » sera créée.", "Warning"));
        foreach (var w in newWarehouses)
            issues.Add(new ImportIssue(0, "Warehouse", $"Le nouvel entrepôt « {w} » sera créé.", "Warning"));
        if (issues.Count >= MaxIssues)
            issues.Add(new ImportIssue(0, null, $"Validation arrêtée après {MaxIssues} anomalies. Corrigez d'abord celles-ci.", "Error"));

        return new ValidationOutcome(issues, rows, sheet.Rows.Count, sheet.Headers, samples);
    }

    private static string Key(object row) => row switch
    {
        SupplierImportRow r => r.Code,
        ProductImportRow r => r.CArtSap,
        SalesImportRow r => $"{r.MonthKey}|{r.CArtSap}|{r.Agency}",
        InventoryImportRow r => $"{r.DateKey}|{r.CArtSap}|{r.Warehouse}",
        SupplyImportRow r => $"{r.PoNumber}|{r.CArtSap}",
        ForecastImportRow r => $"{r.CArtSap}|{r.MonthKey}",
        _ => Guid.NewGuid().ToString(),
    };

    private static SupplierImportRow? SupplierRow(RowContext c, ImportLookups l)
    {
        var code = c.Text("Supplier Code");
        var name = c.Text("Supplier Name");
        var country = c.Text("Country");
        var transit = c.Int("Transit Days", min: 0, max: 365);
        var lead = c.Int("Production Lead Days", min: 0, max: 365);
        string? countryCode = null;
        if (country is not null)
        {
            countryCode = ResolveCountry(country, l);
            if (countryCode is null) c.Error("Country", $"Pays inconnu : « {country} ». Utilisez un code ISO (ex. TR, CN) ou un nom de pays connu.");
        }
        return c.HasError ? null : new SupplierImportRow(code!, name!, countryCode!, transit, lead);
    }

    private static ProductImportRow? ProductRow(RowContext c, ImportLookups l, Dictionary<string, MaterialType?> newCategories, HashSet<string> fileProducts)
    {
        var cartSap = c.Text("CArtSAP");
        var description = c.Text("Description");
        var category = c.Text("Category");
        var typeText = c.Text("Material Type");
        var type = CellParser.ParseMaterialType(typeText);
        if (typeText is not null && type is null)
            c.Error("Material Type", $"Type d'article inconnu : « {typeText} ». Utilisez Produit fini, Matière première ou Emballage.");

        string? categoryCode = null;
        MaterialType? newCategoryType = null;
        if (category is not null)
        {
            var key = category.Trim().ToUpperInvariant();
            if (l.CategoryCodes.Contains(key)) categoryCode = key;
            else if (l.CategoryNameToCode.TryGetValue(category.Trim(), out var byName)) categoryCode = byName;
            else if (type is null) c.Error("Category", $"La nouvelle catégorie « {category} » nécessite un Material Type sur cette ligne.");
            else
            {
                categoryCode = key;
                newCategoryType = type;
                newCategories.TryAdd(key, type);
            }
        }

        var supplier = c.Text("Main Supplier");
        string? supplierCode = null;
        if (supplier is not null)
        {
            supplierCode = ResolveSupplier(supplier, l);
            if (supplierCode is null) c.Error("Main Supplier", $"Fournisseur inconnu : « {supplier} ». Importez d'abord le référentiel fournisseurs.");
        }

        var unit = c.Text("Unit")?.ToUpperInvariant();
        var materialType = type ?? MaterialType.FinishedGood;
        var row = new ProductImportRow(cartSap ?? "", description ?? "", categoryCode ?? "", newCategoryType, materialType,
            c.Text("Brand"), unit ?? (materialType == MaterialType.FinishedGood ? "CTN" : "KG"),
            c.Number("Unit Weight", positive: true), c.Number("Colisage", positive: true), c.Number("TC Conversion", positive: true),
            c.Number("Unit Cost"), c.Number("Safety Stock"), supplierCode, c.Text("Format"), c.Text("Color"));
        if (cartSap is not null) fileProducts.Add(cartSap);
        return c.HasError ? null : row;
    }

    private static SalesImportRow? SalesRow(RowContext c, ImportLookups l, HashSet<string> newAgencies)
    {
        var month = c.Month("Date");
        var cartSap = c.KnownProduct(l);
        var agency = c.Text("Agency");
        var forecast = c.Number("Forecast");
        var actual = c.Number("Actual");
        var ordered = c.Number("Ordered");
        if (agency is not null && !l.AgencyNames.Contains(agency)) newAgencies.Add(agency);
        return c.HasError ? null : new SalesImportRow(DateKeys.MonthKey(month!.Value), cartSap!, agency!, forecast!.Value, actual!.Value, ordered);
    }

    private static InventoryImportRow? InventoryRow(RowContext c, ImportLookups l, HashSet<string> newWarehouses)
    {
        var date = c.Date("Date");
        var cartSap = c.KnownProduct(l);
        var stock = c.Number("Stock");
        var warehouse = c.Text("Warehouse");
        if (warehouse is not null && !l.WarehouseNames.Contains(warehouse)) newWarehouses.Add(warehouse);
        return c.HasError ? null : new InventoryImportRow(DateKeys.ToKey(date!.Value), cartSap!, warehouse!, stock!.Value);
    }

    private static SupplyImportRow? SupplyRow(RowContext c, ImportLookups l)
    {
        var po = c.Text("PO");
        var cartSap = c.KnownProduct(l);
        var supplierText = c.Text("Supplier");
        string? supplier = null;
        if (supplierText is not null)
        {
            supplier = ResolveSupplier(supplierText, l);
            if (supplier is null) c.Error("Supplier", $"Fournisseur inconnu : « {supplierText} ». Importez d'abord le référentiel fournisseurs.");
        }
        var qty = c.Number("Quantity", positive: true);
        var countryText = c.Text("Country");
        string? country = null;
        if (countryText is not null)
        {
            country = ResolveCountry(countryText, l);
            if (country is null) c.Error("Country", $"Pays inconnu : « {countryText} ».");
        }
        var etd = c.Date("ETD");
        var eta = c.Date("ETA");
        var statusText = c.Text("Status");
        var status = CellParser.ParseStatus(statusText);
        if (statusText is not null && status is null)
            c.Error("Status", $"Statut inconnu : « {statusText} ». Valeurs attendues : {string.Join(", ", Enum.GetValues<SupplyStatus>().Select(Labels.Of))}.");
        var orderDate = c.Date("Order Date");
        var required = c.Date("Required Date");
        var arrival = c.Date("Actual Arrival");
        var delivered = c.Number("Delivered Qty");
        var containers = c.Number("TC");

        if (etd is { } d1 && eta is { } d2 && d2 < d1) c.Error("ETA", $"L'ETA du {d2:dd/MM/yyyy} précède l'ETD du {d1:dd/MM/yyyy}.");
        if (orderDate is { } o && etd is { } e && e < o) c.Error("ETD", "L'ETD précède la date de commande.");
        if (status == SupplyStatus.Delivered && arrival is null) c.Error("Actual Arrival", "Une ligne livrée doit avoir une date Actual Arrival.");
        if (status is { } st && st != SupplyStatus.Delivered && st != SupplyStatus.Cancelled && eta is null && etd is null)
            c.Warn("ETA", "Ligne ouverte sans ETD/ETA : son risque ne peut pas être évalué.");

        return c.HasError ? null : new SupplyImportRow(po!, cartSap!, supplier!, qty!.Value, country,
            orderDate ?? etd ?? eta ?? DateOnly.FromDateTime(DateTime.UtcNow), required, etd, eta, arrival, status!.Value, delivered, containers,
            c.Text("Port"), c.Text("Booking"), c.Text("BL"), c.Text("Customs Status"));
    }

    private static ForecastImportRow? ForecastRow(RowContext c, ImportLookups l)
    {
        var cartSap = c.KnownProduct(l);
        var month = c.Month("Month");
        var forecast = c.Number("Forecast");
        return c.HasError ? null : new ForecastImportRow(cartSap!, DateKeys.MonthKey(month!.Value), forecast!.Value);
    }

    private static string? ResolveSupplier(string value, ImportLookups l)
    {
        var v = value.Trim();
        if (l.SupplierCodes.Contains(v)) return l.SupplierCodes.First(c => string.Equals(c, v, StringComparison.OrdinalIgnoreCase));
        return l.SupplierNameToCode.TryGetValue(v, out var code) ? code : null;
    }

    private static string? ResolveCountry(string value, ImportLookups l)
    {
        var v = value.Trim();
        if (l.CountryCodes.Contains(v.ToUpperInvariant())) return v.ToUpperInvariant();
        return l.CountryNameToCode.TryGetValue(v, out var code) ? code : null;
    }

    /// <summary>Cell access for one row, collecting issues as it goes.</summary>
    private sealed class RowContext(ImportDefinition def, RawRow row, IReadOnlyDictionary<string, int> index, List<ImportIssue> issues)
    {
        public bool HasError { get; private set; }

        private ColumnDef Col(string name) => def.Columns.First(c => c.Name == name);

        private object? Raw(string column) =>
            index.TryGetValue(column, out var i) && i < row.Cells.Count ? row.Cells[i] : null;

        public void Error(string? column, string message)
        {
            HasError = true;
            issues.Add(new ImportIssue(row.ExcelRow, column, message, "Error"));
        }

        public void Warn(string? column, string message) => issues.Add(new ImportIssue(row.ExcelRow, column, message, "Warning"));

        private bool MissingRequired(string column)
        {
            if (!CellParser.IsBlank(Raw(column)) || !Col(column).Required) return false;
            Error(column, $"Valeur manquante pour « {column} ».");
            return true;
        }

        public string? Text(string column)
        {
            if (MissingRequired(column)) return null;
            var t = CellParser.Text(Raw(column));
            if (t is { Length: > 200 }) { Error(column, "Valeur trop longue (200 caractères maximum)."); return null; }
            return t;
        }

        public double? Number(string column, bool positive = false)
        {
            if (MissingRequired(column)) return null;
            var raw = Raw(column);
            if (CellParser.IsBlank(raw)) return null;
            if (!CellParser.TryNumber(raw, out var v)) { Error(column, $"« {CellParser.Text(raw)} » n'est pas un nombre."); return null; }
            if (v < 0) { Error(column, $"La valeur négative {v} n'est pas autorisée."); return null; }
            if (positive && v == 0) { Error(column, "La valeur doit être supérieure à zéro."); return null; }
            return v;
        }

        public int? Int(string column, int min, int max)
        {
            var v = Number(column);
            if (v is null) return null;
            if (v != Math.Floor(v.Value) || v < min || v > max) { Error(column, $"Nombre entier attendu entre {min} et {max}."); return null; }
            return (int)v.Value;
        }

        public DateOnly? Date(string column)
        {
            if (MissingRequired(column)) return null;
            var raw = Raw(column);
            if (CellParser.IsBlank(raw)) return null;
            if (!CellParser.TryDate(raw, out var d)) { Error(column, $"Date invalide : « {CellParser.Text(raw)} ». Utilisez jj/mm/aaaa."); return null; }
            return d;
        }

        public DateOnly? Month(string column)
        {
            if (MissingRequired(column)) return null;
            var raw = Raw(column);
            if (CellParser.IsBlank(raw)) return null;
            if (!CellParser.TryMonth(raw, out var d)) { Error(column, $"Mois invalide : « {CellParser.Text(raw)} ». Utilisez une date ou mm/aaaa."); return null; }
            return d;
        }

        public string? KnownProduct(ImportLookups l)
        {
            var cartSap = Text("CArtSAP");
            if (cartSap is null) return null;
            if (!l.ProductCodes.Contains(cartSap))
            {
                Error("CArtSAP", l.HasDemoData && l.ProductCodes.Count == 0
                    ? $"CArtSAP inconnu : « {cartSap} ». Seuls des produits de DÉMO existent : importez d'abord le référentiel produits."
                    : $"CArtSAP inconnu : « {cartSap} ».");
                return null;
            }
            return cartSap;
        }
    }
}

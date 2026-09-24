using Broli.SOP.Application.Abstractions;
using Broli.SOP.Application.Import;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Tests;

public class ImportValidatorTests
{
    private static readonly StringComparer Ci = StringComparer.OrdinalIgnoreCase;

    private static ImportLookups Lookups(bool demo = false, params string[] products) => new(
        products.ToHashSet(Ci), new HashSet<string>(["SUP-1"], Ci), new Dictionary<string, string>(Ci) { ["Anatolia Films"] = "SUP-1" },
        new Dictionary<string, string>(Ci) { ["Turkey"] = "TR" }, new HashSet<string>(["TR", "CM"], Ci),
        new Dictionary<string, string>(Ci) { ["Films"] = "FILMS" }, new HashSet<string>(["FILMS"], Ci),
        new HashSet<string>(["Douala"], Ci), new HashSet<string>(["Douala Central"], Ci), demo);

    private static RawSheet Sheet(string[] headers, params object?[][] rows) =>
        new(headers, rows.Select((r, i) => new RawRow(i + 2, r)).ToList());

    private static ValidationOutcome Validate(ImportType type, RawSheet sheet, ImportLookups? lookups = null) =>
        ImportValidator.Validate(ImportDefinitions.Get(type), sheet, lookups ?? Lookups(false, "100245", "300101"));

    [Fact]
    public void Valid_sales_file_passes_with_aliases_and_french_numbers()
    {
        var o = Validate(ImportType.Sales, Sheet(["Mois", "Code article", "Agence", "Prévision", "Ventes"],
            [new DateTime(2026, 9, 15), "100245", "Douala", "1 200,5", 1130.0]));
        Assert.Equal(0, o.ErrorCount);
        var row = Assert.IsType<SalesImportRow>(Assert.Single(o.ValidRows));
        Assert.Equal(20260901, row.MonthKey);
        Assert.Equal(1200.5, row.Forecast);
    }

    [Fact]
    public void Missing_required_column_blocks_everything()
    {
        var o = Validate(ImportType.Inventory, Sheet(["Date", "CArtSAP", "Warehouse"], [new DateTime(2026, 9, 30), "100245", "Douala Central"]));
        Assert.Contains(o.Issues, i => i.Severity == "Error" && i.Message.Contains("Colonne obligatoire manquante : « Stock »"));
        Assert.Empty(o.ValidRows);
    }

    [Fact]
    public void Detects_invalid_dates_negative_values_unknown_codes_and_duplicates()
    {
        var o = Validate(ImportType.Inventory, Sheet(["Date", "CArtSAP", "Stock", "Warehouse"],
            [new DateTime(2026, 9, 30), "100245", 100.0, "Douala Central"],
            ["31/02/2026", "100245", 100.0, "Douala Central"],
            [new DateTime(2026, 9, 30), "100245", -5.0, "Douala Central"],
            [new DateTime(2026, 9, 30), "999999", 10.0, "Douala Central"],
            [new DateTime(2026, 9, 30), "100245", 50.0, "Douala Central"],
            [new DateTime(2026, 9, 30), "300101", "abc", "Douala Central"],
            [new DateTime(2026, 9, 30), null, 10.0, "Douala Central"]));

        Assert.Contains(o.Issues, i => i.Row == 3 && i.Message.StartsWith("Date invalide"));
        Assert.Contains(o.Issues, i => i.Row == 4 && i.Message.StartsWith("La valeur négative"));
        Assert.Contains(o.Issues, i => i.Row == 5 && i.Message.StartsWith("CArtSAP inconnu"));
        Assert.Contains(o.Issues, i => i.Row == 6 && i.Message.StartsWith("Doublon de la ligne 2"));
        Assert.Contains(o.Issues, i => i.Row == 7 && i.Message.Contains("n'est pas un nombre"));
        Assert.Contains(o.Issues, i => i.Row == 8 && i.Message.StartsWith("Valeur manquante"));
        Assert.Single(o.ValidRows);
    }

    [Fact]
    public void Supply_checks_supplier_status_and_date_order()
    {
        var headers = new[] { "PO", "CArtSAP", "Supplier", "Quantity", "ETD", "ETA", "Status" };
        var o = Validate(ImportType.Supply, Sheet(headers,
            ["4500001", "300101", "Anatolia Films", 25000.0, new DateTime(2026, 9, 5), new DateTime(2026, 10, 8), "Shipped"],
            ["4500002", "300101", "Unknown Ltd", 1000.0, new DateTime(2026, 9, 5), new DateTime(2026, 10, 8), "Shipped"],
            ["4500003", "300101", "SUP-1", 1000.0, new DateTime(2026, 10, 5), new DateTime(2026, 9, 8), "Shipped"],
            ["4500004", "300101", "SUP-1", 1000.0, null, null, "Teleported"],
            ["4500005", "300101", "SUP-1", 1000.0, new DateTime(2026, 9, 5), new DateTime(2026, 10, 8), "Delivered"]));

        Assert.Equal(SupplyStatus.Shipped, Assert.IsType<SupplyImportRow>(o.ValidRows[0]).Status);
        Assert.Contains(o.Issues, i => i.Row == 3 && i.Message.StartsWith("Fournisseur inconnu"));
        Assert.Contains(o.Issues, i => i.Row == 4 && i.Message.Contains("précède l'ETD"));
        Assert.Contains(o.Issues, i => i.Row == 5 && i.Message.StartsWith("Statut inconnu"));
        Assert.Contains(o.Issues, i => i.Row == 6 && i.Message.Contains("doit avoir une date Actual Arrival"));
    }

    [Fact]
    public void Facts_are_rejected_while_only_demo_products_exist()
    {
        var o = Validate(ImportType.Forecast, Sheet(["CArtSAP", "Month", "Forecast"], ["100245", "10/2026", 1250.0]), Lookups(demo: true));
        Assert.Contains(o.Issues, i => i.Message.Contains("importez d'abord le référentiel produits"));
    }

    [Fact]
    public void Product_master_creates_categories_only_with_a_material_type()
    {
        var o = Validate(ImportType.ProductMaster, Sheet(["CArtSAP", "Description", "Category", "Material Type", "Brand"],
            ["100245", "SPAGHETTI RAHMA 500G", "SPAGHETTI", "Produit fini", "Rahma"],
            ["100246", "MACARONI RAHMA 500G", "MACARONI", null, "Rahma"],
            ["300101", "FILM RAHMA", "Films", null, "Rahma"]));
        Assert.Equal(2, o.ValidRows.Count);
        Assert.Contains(o.Issues, i => i.Severity == "Warning" && i.Message.Contains("nouvelle catégorie « SPAGHETTI »"));
        Assert.Contains(o.Issues, i => i.Row == 3 && i.Message.Contains("nécessite un Material Type"));
        Assert.Equal(MaterialType.FinishedGood, Assert.IsType<ProductImportRow>(o.ValidRows[0]).NewCategoryMaterialType);
    }

    [Fact]
    public void Empty_sheet_is_an_error()
    {
        var o = Validate(ImportType.Forecast, Sheet(["CArtSAP", "Month", "Forecast"]));
        Assert.Equal(1, o.ErrorCount);
    }
}

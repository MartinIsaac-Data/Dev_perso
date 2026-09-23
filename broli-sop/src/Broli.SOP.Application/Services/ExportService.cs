namespace Broli.SOP.Application.Services;

/// <summary>
/// Exports exactly what the user is looking at: the global filter plus the table's search/view,
/// all pages, no more. Monetary columns are only included with the finance permission.
/// </summary>
public sealed class ExportService(
    InventoryService inventory,
    DemandService demand,
    SupplyService supply,
    RiskService risks,
    ITabularExporter exporter,
    IAuditLogger audit,
    ICurrentUser user,
    IAnalyticsEngine engine)
{
    public static readonly string[] Datasets = ["inventory", "demand", "supply", "risks", "risk-register"];

    public async Task<(byte[] Content, string FileName, string ContentType)?> ExportAsync(
        string dataset, string format, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var table = await BuildAsync(dataset, filter, q, ct);
        if (table is null) return null;

        var csv = string.Equals(format, "csv", StringComparison.OrdinalIgnoreCase);
        var bytes = csv ? exporter.ToCsv(table) : exporter.ToXlsx(table);
        var name = $"broli-sop-{dataset}-{DateTime.UtcNow:yyyyMMdd-HHmm}.{(csv ? "csv" : "xlsx")}";
        await audit.LogAsync("Exported data", "Export", dataset, null, $"{table.Rows.Count} rows, {format}; {filter.ToQueryString()}", ct);
        return (bytes, name, csv ? "text/csv" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    }

    private async Task<TableData?> BuildAsync(string dataset, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var period = (await engine.GetSnapshotAsync(filter, ct)).Period.Info.Label;
        var subtitle = $"Period: {period} · Filters: {(filter.ToQueryString() is { Length: > 0 } f ? Uri.UnescapeDataString(f) : "none")}"
                       + (string.IsNullOrWhiteSpace(q.Search) ? "" : $" · Search: {q.Search}")
                       + (string.IsNullOrWhiteSpace(q.View) ? "" : $" · View: {q.View}");

        switch (dataset.ToLowerInvariant())
        {
            case "inventory":
            {
                var rows = await inventory.GetAllRowsAsync(filter, q, ct);
                var cols = new List<TableColumn>
                {
                    new("CArtSAP"), new("Description"), new("Category"), new("Brand"), new("Material Type"), new("Unit"),
                    new("Opening Stock", "number"), new("Receipts", "number"), new("Consumption", "number"), new("Closing Stock", "number"),
                    new("Closing TC", "decimal"), new("Safety Stock", "number"), new("Avg Consumption / month", "number"),
                    new("Coverage (months)", "decimal"), new("Coverage Status"), new("Excess", "number"), new("Below Safety"), new("At Risk"),
                    new("Open Supply", "number"), new("In Transit", "number"), new("Next ETA", "date"), new("Projected Stockout", "date"),
                };
                if (finance) cols.Add(new("Stock Value", "number"));
                return new TableData("Inventory & Coverage", subtitle, cols, rows.Select(r =>
                {
                    var v = new List<object?> { r.CArtSap, r.Description, r.Category, r.Brand, r.MaterialType, r.Unit, r.OpeningStock, r.Receipts,
                        r.Consumption, r.ClosingStock, r.ClosingTc, r.SafetyStock, r.AvgMonthlyConsumption, r.CoverageMonths, r.CoverageStatus,
                        r.ExcessStock, r.BelowSafety ? "Yes" : "No", r.AtRisk ? "Yes" : "No", r.OpenSupplyQty, r.InTransitQty, r.NextEta, r.StockoutDate };
                    if (finance) v.Add(r.StockValue);
                    return v.ToArray();
                }).ToList());
            }
            case "demand":
            {
                var rows = await demand.GetAllRowsAsync(filter, q, ct);
                return new TableData("Forecast vs Actual", subtitle,
                    [new("CArtSAP"), new("Description"), new("Category"), new("Brand"), new("Unit"), new("Forecast", "number"), new("Actual", "number"),
                     new("Variance", "number"), new("Variance %", "decimal"), new("Accuracy %", "decimal"), new("BIAS %", "decimal"), new("Status")],
                    rows.Select(r => new object?[] { r.CArtSap, r.Description, r.Category, r.Brand, r.Unit, r.Forecast, r.Actual, r.Variance,
                        r.VariancePct, r.AccuracyPct, r.BiasPct, r.Status }).ToList());
            }
            case "supply":
            {
                var rows = await supply.GetAllRowsAsync(filter, q, ct);
                return new TableData("Supply & Open Orders", subtitle,
                    [new("PO"), new("CArtSAP"), new("Product"), new("Supplier"), new("Country"), new("Quantity", "number"), new("Unit"), new("TC", "decimal"),
                     new("Order Date", "date"), new("Required Date", "date"), new("ETD", "date"), new("ETA", "date"), new("Actual Arrival", "date"),
                     new("Status"), new("Delay (days)", "number"), new("Transit (days)", "number"), new("Projected Stockout", "date"), new("Risk"),
                     new("Risk Reason"), new("Port"), new("Booking"), new("BL"), new("Customs")],
                    rows.Select(r => new object?[] { r.PoNumber, r.CArtSap, r.Product, r.Supplier, r.Country, r.Quantity, r.Unit, r.Tc, r.OrderDate,
                        r.RequiredDate, r.Etd, r.Eta, r.ActualArrival, r.Status, r.DelayDays, r.TransitDays, r.StockoutDate, r.RiskLevel, r.RiskReason,
                        r.Port, r.Booking, r.BillOfLading, r.CustomsStatus }).ToList());
            }
            case "risks":
            {
                IEnumerable<DetectedRisk> rows = await risks.GetDetectedAsync(filter, ct);
                rows = TableHelper.Filter(rows, q, r => $"{r.Category} {r.Severity} {r.CArtSap} {r.Product} {r.Title} {r.Reference}");
                if (!string.IsNullOrWhiteSpace(q.View)) rows = rows.Where(r => string.Equals(r.Category, q.View, StringComparison.OrdinalIgnoreCase)
                                                                               || string.Equals(r.Severity, q.View, StringComparison.OrdinalIgnoreCase));
                return new TableData("Detected Risks", subtitle,
                    [new("Severity"), new("Category"), new("CArtSAP"), new("Product"), new("Risk"), new("Detail"), new("Suggested Action"), new("Reference"), new("Due By", "date")],
                    rows.Select(r => new object?[] { r.Severity, r.Category, r.CArtSap, r.Product, r.Title, r.Detail, r.SuggestedAction, r.Reference, r.DueBy }).ToList());
            }
            case "risk-register":
            {
                var rows = await risks.GetAllRegisterAsync(q, ct);
                return new TableData("Risk & Opportunity Register", subtitle,
                    [new("Risk ID"), new("Category"), new("Type"), new("Description"), new("CArtSAP"), new("Product"), new("Impact"), new("Probability %", "number"),
                     new("Score", "number"), new("Owner"), new("Action"), new("Due Date", "date"), new("Status")],
                    rows.Select(r => new object?[] { r.Code, r.Category, r.IsOpportunity ? "Opportunity" : "Risk", r.Description, r.CArtSap, r.Product, r.Impact,
                        r.Probability, r.Score, r.Owner, r.Action, r.DueDate, r.Status }).ToList());
            }
            default:
                return null;
        }
    }
}

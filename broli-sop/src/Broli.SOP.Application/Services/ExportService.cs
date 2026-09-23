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
    MrpService mrp,
    MaterialsService materials,
    TransitService transit,
    SupplierService suppliers,
    ActionService actions,
    ITabularExporter exporter,
    IAuditLogger audit,
    ICurrentUser user,
    IAnalyticsEngine engine)
{
    public static readonly string[] Datasets = ["inventory", "demand", "supply", "risks", "risk-register", "mrp", "raw-materials", "films", "finished-goods", "transit", "suppliers", "actions"];

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
            case "mrp":
            {
                var rows = await mrp.GetAllRowsAsync(filter, q, ct);
                var horizon = rows.FirstOrDefault()?.Forecast.Count ?? 0;
                var cols = new List<TableColumn> { new("CArtSAP"), new("Description"), new("Category"), new("Material Type"), new("Unit"), new("Supplier"), new("Opening Stock", "number") };
                cols.AddRange(Enumerable.Range(1, horizon).Select(i => new TableColumn($"Forecast M+{i}", "number")));
                cols.AddRange([new("Open Order", "number"), new("In Transit", "number"), new("Safety Stock", "number"), new("Projected Stock", "number"),
                    new("Coverage (months)", "decimal"), new("Coverage Status"), new("Net Requirement", "number"), new("Recommended Order", "number"),
                    new("Recommended TC", "decimal"), new("Lead Time (days)", "number"), new("Need Date", "date"), new("Order By", "date"), new("Days Late", "number"), new("Risk")]);
                if (finance) cols.Add(new("Recommended Value", "number"));
                return new TableData("MRP — Net Requirements", subtitle, cols, rows.Select(r =>
                {
                    var v = new List<object?> { r.CArtSap, r.Description, r.Category, r.MaterialType, r.Unit, r.Supplier, r.OpeningStock };
                    v.AddRange(r.Forecast.Cast<object?>());
                    v.AddRange([r.OpenOrder, r.InTransit, r.SafetyStock, r.ProjectedStock, r.CoverageMonths, r.CoverageStatus, r.NetRequirement,
                        r.RecommendedOrder, r.RecommendedTc, r.LeadTimeDays, r.NeedDate, r.OrderByDate, r.DaysLate, r.Risk]);
                    if (finance) v.Add(r.RecommendedValue);
                    return v.ToArray();
                }).ToList());
            }
            case "raw-materials" or "films" or "finished-goods":
            {
                var rows = await materials.GetAllRowsAsync(dataset, filter, q, ct);
                var cols = new List<TableColumn>
                {
                    new("CArtSAP"), new("Description"), new("Category"), new("Brand"), new("Material Type"), new("Format"), new("Color"), new("Supplier"),
                    new("Country"), new("Unit"), new("Stock", "number"), new("Stock TC", "decimal"), new("Avg Consumption / month", "number"),
                    new("Forecast (period)", "number"), new("Actual (period)", "number"), new("Production (period)", "number"), new("Service Level %", "decimal"),
                    new("Coverage (months)", "decimal"), new("Coverage Status"), new("Open PO", "number"), new("In Transit", "number"), new("Next ETA", "date"),
                    new("Projected Stockout", "date"), new("Flags"), new("Risk"),
                };
                if (finance) { cols.Add(new("Unit Cost", "decimal")); cols.Add(new("Stock Value", "number")); }
                return new TableData(dataset switch { "films" => "Films", "finished-goods" => "Finished Goods", _ => "Raw Materials & Packaging" }, subtitle, cols,
                    rows.Select(r =>
                    {
                        var v = new List<object?> { r.CArtSap, r.Description, r.Category, r.Brand, r.MaterialType, r.Format, r.Color, r.Supplier, r.Country, r.Unit,
                            r.Stock, r.StockTc, r.AvgConsumption, r.Forecast, r.Actual, r.Production, r.ServiceLevelPct, r.CoverageMonths, r.CoverageStatus,
                            r.OpenPo, r.InTransit, r.NextEta, r.StockoutDate, string.Join(", ", r.Flags), r.Risk };
                        if (finance) { v.Add(r.UnitCost); v.Add(r.StockValue); }
                        return v.ToArray();
                    }).ToList());
            }
            case "transit":
            {
                var rows = await transit.GetAllRowsAsync(filter, q, ct);
                return new TableData("Logistics & Transit", subtitle,
                    [new("PO"), new("Supplier"), new("Material"), new("Quantity", "number"), new("Unit"), new("TC", "decimal"), new("Country"), new("Port"),
                     new("Booking"), new("BL"), new("ETD", "date"), new("ETA", "date"), new("Actual Arrival", "date"), new("Status"), new("Customs Status"),
                     new("Clearing"), new("Estimated Delivery", "date"), new("Transit (days)", "number"), new("Standard (days)", "number"),
                     new("Gap (days)", "number"), new("Delay (days)", "number"), new("Risk")],
                    rows.Select(r => new object?[] { r.PoNumber, r.Supplier, r.Material, r.Quantity, r.Unit, r.Tc, r.Country, r.Port, r.Booking, r.BillOfLading,
                        r.Etd, r.Eta, r.ActualArrival, r.Status, r.CustomsStatus, r.Clearing, r.EstimatedDelivery, r.TransitDays, r.StandardTransitDays,
                        r.TransitGapDays, r.DelayDays, r.Risk }).ToList());
            }
            case "suppliers":
            {
                IEnumerable<SupplierRow> rows = await suppliers.GetRowsAsync(filter, ct);
                rows = TableHelper.Filter(rows, q, r => $"{r.Code} {r.Name} {r.Country} {r.Risk}");
                return new TableData("Supplier Performance", subtitle + " · " + SupplierService.Window,
                    [new("Code"), new("Supplier"), new("Country"), new("Orders", "number"), new("Delivered", "number"), new("On Time %", "decimal"),
                     new("Avg Delay (days)", "decimal"), new("Partial Deliveries", "number"), new("Open Orders", "number"), new("In Transit TC", "decimal"),
                     new("Avg Transit (days)", "decimal"), new("Standard Transit (days)", "number"), new("Late Open", "number"), new("Critical Open", "number"), new("Risk")],
                    rows.Select(r => new object?[] { r.Code, r.Name, r.Country, r.Orders, r.Delivered, r.OnTimePct, r.AvgDelayDays, r.PartialDeliveries,
                        r.OpenOrders, r.InTransitTc, r.AvgTransitDays, r.StandardTransitDays, r.LateOpen, r.CriticalOpen, r.Risk }).ToList());
            }
            case "actions":
            {
                var rows = await actions.ListAllAsync(new ActionQuery { Search = q.Search, View = q.View, Sort = q.Sort, Desc = q.Desc }, ct);
                return new TableData("S&OP Action Plan", subtitle,
                    [new("Action ID"), new("Date", "date"), new("Topic"), new("Description"), new("Owner"), new("Department"), new("Due Date", "date"),
                     new("Priority"), new("Status"), new("Decision"), new("Risk"), new("CArtSAP"), new("Comment")],
                    rows.Select(a => new object?[] { a.Code, a.Date, a.Topic, a.Description, a.Owner, a.Department, a.DueDate, a.Priority,
                        a.Status + (a.IsOverdue ? " (overdue)" : ""), a.IsDecision ? "Yes" : "No", a.RiskCode, a.CArtSap, a.Comment }).ToList());
            }
            default:
                return null;
        }
    }
}

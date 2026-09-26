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
    Reporting.ReportingService reporting,
    ITabularExporter exporter,
    IAuditLogger audit,
    ICurrentUser user,
    IAnalyticsEngine engine)
{
    public static readonly string[] Datasets = ["inventory", "demand", "supply", "risks", "risk-register", "mrp", "raw-materials", "films", "finished-goods", "transit", "suppliers", "actions", "reporting"];

    public async Task<(byte[] Content, string FileName, string ContentType)?> ExportAsync(
        string dataset, string format, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var table = await BuildAsync(dataset, filter, q, ct);
        if (table is null) return null;

        var csv = string.Equals(format, "csv", StringComparison.OrdinalIgnoreCase);
        var bytes = csv ? exporter.ToCsv(table) : exporter.ToXlsx(table);
        var name = $"broli-sop-{dataset}-{DateTime.UtcNow:yyyyMMdd-HHmm}.{(csv ? "csv" : "xlsx")}";
        await audit.LogAsync("Données exportées", "Export", dataset, null, $"{table.Rows.Count} lignes, {format} ; {filter.ToQueryString()}", ct);
        return (bytes, name, csv ? "text/csv" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    }

    private async Task<TableData?> BuildAsync(string dataset, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var period = (await engine.GetSnapshotAsync(filter, ct)).Period.Info.Label;
        var subtitle = $"Période : {period} · Filtres : {(filter.ToQueryString() is { Length: > 0 } f ? Uri.UnescapeDataString(f) : "aucun")}"
                       + (string.IsNullOrWhiteSpace(q.Search) ? "" : $" · Recherche : {q.Search}")
                       + (string.IsNullOrWhiteSpace(q.View) ? "" : $" · Vue : {q.View}");

        switch (dataset.ToLowerInvariant())
        {
            case "inventory":
            {
                var rows = await inventory.GetAllRowsAsync(filter, q, ct);
                var cols = new List<TableColumn>
                {
                    new("CArtSAP"), new("Désignation"), new("Catégorie"), new("Marque"), new("Type d'article"), new("Unité"),
                    new("Stock initial", "number"), new("Réceptions", "number"), new("Consommation", "number"), new("Stock final", "number"),
                    new("TC final", "decimal"), new("Stock de sécurité", "number"), new("Conso. moyenne / mois", "number"),
                    new("Couverture (mois)", "decimal"), new("Statut couverture"), new("Excédent", "number"), new("Sous le stock de sécurité"), new("À risque"),
                    new("Appro ouvert", "number"), new("En transit", "number"), new("Prochaine ETA", "date"), new("Rupture prévue", "date"),
                };
                if (finance) cols.Add(new("Valeur du stock", "number"));
                return new TableData("Stock et couverture", subtitle, cols, rows.Select(r =>
                {
                    var v = new List<object?> { r.CArtSap, r.Description, r.Category, r.Brand, r.MaterialType, r.Unit, r.OpeningStock, r.Receipts,
                        r.Consumption, r.ClosingStock, r.ClosingTc, r.SafetyStock, r.AvgMonthlyConsumption, r.CoverageMonths, r.CoverageStatus,
                        r.ExcessStock, r.BelowSafety ? "Oui" : "Non", r.AtRisk ? "Oui" : "Non", r.OpenSupplyQty, r.InTransitQty, r.NextEta, r.StockoutDate };
                    if (finance) v.Add(r.StockValue);
                    return v.ToArray();
                }).ToList());
            }
            case "demand":
            {
                var rows = await demand.GetAllRowsAsync(filter, q, ct);
                return new TableData("Prévision vs réel", subtitle,
                    [new("CArtSAP"), new("Désignation"), new("Catégorie"), new("Marque"), new("Unité"), new("Prévision", "number"), new("Réel", "number"),
                     new("Écart", "number"), new("Écart %", "decimal"), new("Précision %", "decimal"), new("Biais %", "decimal"), new("Statut")],
                    rows.Select(r => new object?[] { r.CArtSap, r.Description, r.Category, r.Brand, r.Unit, r.Forecast, r.Actual, r.Variance,
                        r.VariancePct, r.AccuracyPct, r.BiasPct, r.Status }).ToList());
            }
            case "supply":
            {
                var rows = await supply.GetAllRowsAsync(filter, q, ct);
                return new TableData("Approvisionnement et commandes ouvertes", subtitle,
                    [new("Commande"), new("CArtSAP"), new("Article"), new("Fournisseur"), new("Pays"), new("Quantité", "number"), new("Unité"), new("TC", "decimal"),
                     new("Date de commande", "date"), new("Date de besoin", "date"), new("ETD", "date"), new("ETA", "date"), new("Arrivée réelle", "date"),
                     new("Statut"), new("Retard (j)", "number"), new("Transit (j)", "number"), new("Rupture prévue", "date"), new("Risque"),
                     new("Motif du risque"), new("Port"), new("Booking"), new("BL"), new("Douane")],
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
                return new TableData("Risques détectés", subtitle,
                    [new("Gravité"), new("Catégorie"), new("CArtSAP"), new("Article"), new("Risque"), new("Détail"), new("Action suggérée"), new("Référence"), new("Échéance", "date")],
                    rows.Select(r => new object?[] { r.Severity, r.Category, r.CArtSap, r.Product, r.Title, r.Detail, r.SuggestedAction, r.Reference, r.DueBy }).ToList());
            }
            case "risk-register":
            {
                var rows = await risks.GetAllRegisterAsync(q, ct);
                return new TableData("Registre des risques et opportunités", subtitle,
                    [new("N° risque"), new("Catégorie"), new("Type"), new("Désignation"), new("CArtSAP"), new("Article"), new("Impact"), new("Probabilité %", "number"),
                     new("Score", "number"), new("Responsable"), new("Action"), new("Échéance", "date"), new("Statut")],
                    rows.Select(r => new object?[] { r.Code, r.Category, r.IsOpportunity ? "Opportunité" : "Risque", r.Description, r.CArtSap, r.Product, r.Impact,
                        r.Probability, r.Score, r.Owner, r.Action, r.DueDate, r.Status }).ToList());
            }
            case "mrp":
            {
                var rows = await mrp.GetAllRowsAsync(filter, q, ct);
                var horizon = rows.FirstOrDefault()?.Forecast.Count ?? 0;
                var cols = new List<TableColumn> { new("CArtSAP"), new("Désignation"), new("Catégorie"), new("Type d'article"), new("Unité"), new("Fournisseur"), new("Stock initial", "number") };
                cols.AddRange(Enumerable.Range(1, horizon).Select(i => new TableColumn($"Prévision M+{i}", "number")));
                cols.AddRange([new("Commande ouverte", "number"), new("En transit", "number"), new("Stock de sécurité", "number"), new("Stock projeté", "number"),
                    new("Couverture (mois)", "decimal"), new("Statut couverture"), new("Besoin net", "number"), new("Commande recommandée", "number"),
                    new("TC recommandés", "decimal"), new("Délai (j)", "number"), new("Date de besoin", "date"), new("Commander avant", "date"), new("Jours de retard", "number"), new("Risque")]);
                if (finance) cols.Add(new("Valeur recommandée", "number"));
                return new TableData("MRP — besoins nets", subtitle, cols, rows.Select(r =>
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
                    new("CArtSAP"), new("Désignation"), new("Catégorie"), new("Marque"), new("Type d'article"), new("Format"), new("Couleur"), new("Fournisseur"),
                    new("Pays"), new("Unité"), new("Stock", "number"), new("Stock TC", "decimal"), new("Conso. moyenne / mois", "number"),
                    new("Prévision (période)", "number"), new("Réel (période)", "number"), new("Production (période)", "number"), new("Taux de service %", "decimal"),
                    new("Couverture (mois)", "decimal"), new("Statut couverture"), new("Commandes ouvertes", "number"), new("En transit", "number"), new("Prochaine ETA", "date"),
                    new("Rupture prévue", "date"), new("Alertes"), new("Risque"),
                };
                if (finance) { cols.Add(new("Coût unitaire", "decimal")); cols.Add(new("Valeur du stock", "number")); }
                return new TableData(dataset switch { "films" => "Films", "finished-goods" => "Produits finis", _ => "Matières premières et emballages" }, subtitle, cols,
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
                return new TableData("Logistique et transit", subtitle,
                    [new("Commande"), new("Fournisseur"), new("Article"), new("Quantité", "number"), new("Unité"), new("TC", "decimal"), new("Pays"), new("Port"),
                     new("Booking"), new("BL"), new("ETD", "date"), new("ETA", "date"), new("Arrivée réelle", "date"), new("Statut"), new("Statut douane"),
                     new("Dédouanement"), new("Livraison estimée", "date"), new("Transit (j)", "number"), new("Standard (j)", "number"),
                     new("Écart (j)", "number"), new("Retard (j)", "number"), new("Risque")],
                    rows.Select(r => new object?[] { r.PoNumber, r.Supplier, r.Material, r.Quantity, r.Unit, r.Tc, r.Country, r.Port, r.Booking, r.BillOfLading,
                        r.Etd, r.Eta, r.ActualArrival, r.Status, r.CustomsStatus, r.Clearing, r.EstimatedDelivery, r.TransitDays, r.StandardTransitDays,
                        r.TransitGapDays, r.DelayDays, r.Risk }).ToList());
            }
            case "suppliers":
            {
                IEnumerable<SupplierRow> rows = await suppliers.GetRowsAsync(filter, ct);
                rows = TableHelper.Filter(rows, q, r => $"{r.Code} {r.Name} {r.Country} {r.Risk}");
                return new TableData("Performance fournisseurs", subtitle + " · " + SupplierService.Window,
                    [new("Code"), new("Fournisseur"), new("Pays"), new("Commandes", "number"), new("Livrées", "number"), new("À l'heure %", "decimal"),
                     new("Retard moyen (j)", "decimal"), new("Livraisons partielles", "number"), new("Commandes ouvertes", "number"), new("TC en transit", "decimal"),
                     new("Transit moyen (j)", "decimal"), new("Transit standard (j)", "number"), new("Ouvertes en retard", "number"), new("Ouvertes critiques", "number"), new("Risque")],
                    rows.Select(r => new object?[] { r.Code, r.Name, r.Country, r.Orders, r.Delivered, r.OnTimePct, r.AvgDelayDays, r.PartialDeliveries,
                        r.OpenOrders, r.InTransitTc, r.AvgTransitDays, r.StandardTransitDays, r.LateOpen, r.CriticalOpen, r.Risk }).ToList());
            }
            case "actions":
            {
                var rows = await actions.ListAllAsync(new ActionQuery { Search = q.Search, View = q.View, Sort = q.Sort, Desc = q.Desc }, ct);
                return new TableData("Plan d'actions S&OP", subtitle,
                    [new("N° action"), new("Date", "date"), new("Sujet"), new("Désignation"), new("Responsable"), new("Service"), new("Échéance", "date"),
                     new("Priorité"), new("Statut"), new("Décision"), new("Risque"), new("CArtSAP"), new("Commentaire")],
                    rows.Select(a => new object?[] { a.Code, a.Date, a.Topic, a.Description, a.Owner, a.Department, a.DueDate, a.Priority,
                        a.Status + (a.IsOverdue ? " (en retard)" : ""), a.IsDecision ? "Oui" : "Non", a.RiskCode, a.CArtSap, a.Comment }).ToList());
            }
            case "reporting":
            {
                var (week, rows) = await reporting.GetWeekRowsAsync(q.View, ct);
                IEnumerable<ReportingRow> filtered = TableHelper.Filter(rows, q, r => $"{r.Code} {r.Department} {r.Name} {r.Owner} {r.State} {r.Comments}");
                return new TableData("Suivi des reportings", $"Semaine : {week?.Label ?? "aucune"}" + (string.IsNullOrWhiteSpace(q.Search) ? "" : $" · Recherche : {q.Search}"),
                    [new("N° reporting"), new("Service"), new("Reporting"), new("Responsable"), new("Fréquence"), new("Jour attendu"), new("Heure"),
                     new("Date attendue", "date"), new("Date de réception", "date"), new("Statut"), new("Jours de retard", "number"), new("Qualité"),
                     new("Relance"), new("Commentaire")],
                    filtered.Select(r => new object?[] { r.Code, r.Department, r.Name, r.Owner, r.Frequency, r.ExpectedDay, r.ExpectedTime, r.ExpectedDate,
                        r.ReceivedDate, r.State, r.DaysLate, r.Quality, r.RelanceRequired ? "Oui" : "Non", r.Comments }).ToList());
            }
            default:
                return null;
        }
    }
}

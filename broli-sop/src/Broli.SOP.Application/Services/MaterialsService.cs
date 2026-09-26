namespace Broli.SOP.Application.Services;

/// <summary>
/// One engine for the three material dashboards:
/// raw-materials (raw materials and non-film packaging), films (families listed in configuration), finished-goods.
/// </summary>
public sealed class MaterialsService(IAnalyticsEngine engine, ICurrentUser user)
{
    public static readonly string[] Kinds = ["raw-materials", "films", "finished-goods"];

    public async Task<MaterialsDashboard?> GetDashboardAsync(string kind, SopFilter filter, CancellationToken ct)
    {
        if (!Kinds.Contains(kind)) return null;
        var s = await engine.GetSnapshotAsync(filter, ct);
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var items = Items(s, kind).ToList();
        var rows = items.Select(p => Row(s, p, finance)).ToList();
        var ids = items.Select(p => p.Product.Id).ToHashSet();
        var open = s.OpenLines.Where(l => ids.Contains(l.Product.Id)).ToList();

        var withDemand = items.Where(p => p.AvgConsumption > 0 && p.UnitsPerTc.HasValue).ToList();
        var coverage = KpiMath.SafeDivide(withDemand.Sum(p => p.Tc(p.Available) ?? 0), withDemand.Sum(p => p.Tc(p.AvgConsumption) ?? 0));
        var demand = s.DemandIn(s.Period.MonthKeys).Where(d => ids.Contains(d.ProductId) && d.Ordered.HasValue).ToList();
        var kgStock = items.Where(p => p.Product.Unit.Equals("KG", StringComparison.OrdinalIgnoreCase)).Sum(p => p.Closing);

        var groupByBrand = kind == "films";
        string GroupCode(ProductPosition p) => groupByBrand ? p.Product.Brand ?? "(no brand)" : p.Product.CategoryCode;
        string GroupName(ProductPosition p) => groupByBrand ? p.Product.Brand ?? "(no brand)" : p.Product.CategoryName;
        var rowByCode = rows.ToDictionary(r => r.CArtSap);

        var families = items.GroupBy(p => (GroupCode(p), GroupName(p))).Select(g =>
        {
            var gRows = g.Select(p => rowByCode[p.Product.CArtSap]).ToList();
            var gIds = g.Select(p => p.Product.Id).ToHashSet();
            var gDemand = demand.Where(d => gIds.Contains(d.ProductId));
            var gCov = g.Where(p => p.AvgConsumption > 0 && p.UnitsPerTc.HasValue).ToList();
            return new FamilySummary(g.Key.Item1, g.Key.Item2, g.Count(), Mapping.R(g.Sum(p => p.Tc(p.Closing) ?? 0)),
                Mapping.R(gRows.Sum(r => r.Forecast)), Mapping.R(gRows.Sum(r => r.Actual)), Mapping.R(gRows.Sum(r => r.Production)),
                Mapping.R(KpiMath.ServiceLevelPct(gDemand.Select(d => (d.Ordered!.Value, d.Actual)))),
                Mapping.R(KpiMath.SafeDivide(gCov.Sum(p => p.Tc(p.Available) ?? 0), gCov.Sum(p => p.Tc(p.AvgConsumption) ?? 0))),
                gRows.Count(r => IsAtRisk(r)));
        }).OrderByDescending(f => f.StockTc).ToList();

        return new MaterialsDashboard(
            s.Period.Info, kind, Title(kind), items.Count,
            Mapping.R(items.Sum(p => p.Tc(p.Closing) ?? 0)),
            kgStock > 0 ? Mapping.R(kgStock) : null,
            Mapping.R(coverage),
            Mapping.R(KpiMath.ServiceLevelPct(demand.Select(d => (d.Ordered!.Value, d.Actual)))),
            finance ? Mapping.R(items.Sum(p => p.Value(p.Closing) ?? 0)) : null,
            Mapping.R(open.Where(l => !l.Line.Status.IsInTransit()).Sum(l => l.Tc ?? 0)),
            Mapping.R(open.Where(l => l.Line.Status.IsInTransit()).Sum(l => l.Tc ?? 0)),
            MaterialFlags.All.Select(f => new ChartPoint(f, rows.Count(r => r.Flags.Contains(f)), f)).ToList(),
            families.Select(f => new ChartPoint(f.Name, f.StockTc, f.Code)).Where(c => c.Value > 0).ToList(),
            families,
            s.Settings.Tc.DefaultKgPerTc,
            s.Settings.General.Currency);
    }

    public async Task<PagedResult<MaterialRow>?> GetRowsAsync(string kind, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(kind, filter, q, ct);
        return rows is null ? null : TableHelper.Page(rows, q, SortKeys, Search, "Risk", true);
    }

    public async Task<IReadOnlyList<MaterialRow>> GetAllRowsAsync(string kind, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(kind, filter, q, ct) ?? [];
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, "Risk", true).ToList();
    }

    private async Task<IEnumerable<MaterialRow>?> RowsAsync(string kind, SopFilter filter, TableQuery q, CancellationToken ct)
    {
        if (!Kinds.Contains(kind)) return null;
        var s = await engine.GetSnapshotAsync(filter, ct);
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        IEnumerable<MaterialRow> rows = Items(s, kind).Select(p => Row(s, p, finance)).ToList();
        var view = q.View;
        if (string.IsNullOrWhiteSpace(view) || view == "all") return rows;
        if (view == "at-risk") return rows.Where(IsAtRisk);
        if (view == "raw") return rows.Where(r => r.MaterialType == Labels.Of(MaterialType.RawMaterial));
        if (view == "packaging") return rows.Where(r => r.MaterialType == Labels.Of(MaterialType.Packaging));
        if (view.StartsWith("group:")) { var g = view[6..]; return rows.Where(r => r.Category == g || r.Brand == g); }
        return rows.Where(r => r.Flags.Contains(view, StringComparer.OrdinalIgnoreCase));
    }

    private static string Title(string kind) => kind switch
    {
        "films" => "Tableau de bord films",
        "finished-goods" => "Produits finis",
        _ => "Matières premières et emballages",
    };

    private static IEnumerable<ProductPosition> Items(AnalyticsSnapshot s, string kind)
    {
        var films = s.Settings.General.FilmCategories.ToHashSet(StringComparer.OrdinalIgnoreCase);
        return s.Positions.Values.Where(p => kind switch
        {
            "films" => films.Contains(p.Product.CategoryCode),
            "finished-goods" => p.Product.MaterialType == MaterialType.FinishedGood,
            _ => p.Product.MaterialType != MaterialType.FinishedGood && !films.Contains(p.Product.CategoryCode),
        });
    }

    private static MaterialRow Row(AnalyticsSnapshot s, ProductPosition pos, bool finance)
    {
        var p = pos.Product;
        var months = s.Period.MonthKeys;
        var demand = s.DemandByProduct[p.Id].Where(d => months.Contains(d.MonthKey)).ToList();
        var production = months.Sum(m => s.Production.GetValueOrDefault((p.Id, m)));
        var slowWindow = Math.Max(1, s.Settings.Coverage.SlowMovingMonths);
        var recent = Enumerable.Range(0, slowWindow).Sum(i => s.Consumption.GetValueOrDefault((p.Id, DateKeys.AddMonths(s.Period.AsOfMonthKey, -i))));
        var late = s.OpenLinesByProduct[p.Id].Any(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk);
        var alertDate = MaterialFlags.AlertDate(s.Period.AsOfDate, LeadTimes.ProductLeadDays(p, s.Settings.Supply), s.Settings.Coverage);
        var flags = MaterialFlags.Compute(pos, recent, late, alertDate);

        return new MaterialRow(p.CArtSap, p.Description, p.CategoryName, p.Brand, Labels.Of(p.MaterialType), p.Unit, p.Format, p.Color,
            p.MainSupplierName, p.MainSupplierCode, p.SupplierCountryName,
            Mapping.R(pos.Closing), Mapping.R(pos.Tc(pos.Closing)), Mapping.R(pos.AvgConsumption),
            Mapping.R(demand.Sum(d => d.Forecast)), Mapping.R(demand.Sum(d => d.Actual)), Mapping.R(production),
            Mapping.R(KpiMath.ServiceLevelPct(demand.Where(d => d.Ordered.HasValue).Select(d => (d.Ordered!.Value, d.Actual)))),
            Mapping.R(pos.CoverageMonths), Labels.Of(pos.Status),
            Mapping.R(pos.OpenQty - pos.TransitQty), Mapping.R(pos.TransitQty), pos.NextEta, pos.StockoutDate,
            finance ? p.UnitCost : null, finance ? Mapping.R(pos.Value(pos.Closing)) : null,
            flags, MaterialFlags.Risk(flags));
    }

    private static bool IsAtRisk(MaterialRow r) => Labels.Rank<ImpactLevel>(r.Risk) >= (int)ImpactLevel.High;

    private static string Search(MaterialRow r) => $"{r.CArtSap} {r.Description} {r.Category} {r.Brand} {r.Supplier} {r.Country} {r.Format} {r.Color} {string.Join(' ', r.Flags)}";

    private static readonly Dictionary<string, Func<MaterialRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CArtSap"] = r => r.CArtSap,
        ["Description"] = r => r.Description,
        ["Category"] = r => r.Category,
        ["Brand"] = r => r.Brand,
        ["Format"] = r => r.Format,
        ["Supplier"] = r => r.Supplier,
        ["Country"] = r => r.Country,
        ["Stock"] = r => r.Stock,
        ["StockTc"] = r => r.StockTc,
        ["AvgConsumption"] = r => r.AvgConsumption,
        ["Forecast"] = r => r.Forecast,
        ["Actual"] = r => r.Actual,
        ["Production"] = r => r.Production,
        ["ServiceLevelPct"] = r => r.ServiceLevelPct,
        ["CoverageMonths"] = r => r.CoverageMonths,
        ["OpenPo"] = r => r.OpenPo,
        ["InTransit"] = r => r.InTransit,
        ["NextEta"] = r => r.NextEta,
        ["StockValue"] = r => r.StockValue,
        ["Risk"] = r => Labels.Rank<ImpactLevel>(r.Risk, -1),
    };
}

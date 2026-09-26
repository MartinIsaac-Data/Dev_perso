namespace Broli.SOP.Application.Services;

public sealed class MrpService(IAnalyticsEngine engine, ICurrentUser user)
{
    public async Task<MrpDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var rows = Build(s, finance: user.Has(Contracts.Security.Permissions.FinanceView));
        var horizon = Horizon(s);
        var soon = s.Today.AddDays(7);

        var forecastTc = horizon.Select(m => (double?)Mapping.R(s.Positions.Values.Sum(p => p.Tc(Math.Max(0, s.DemandFn(p.Product.Id)(m))) ?? 0))).ToList();
        var firstMonth = horizon[0];
        var incomingTc = horizon.Select(m => (double?)Mapping.R(s.OpenLines
            .Where(l => Math.Max(DateKeys.MonthKey(l.Line.Eta ?? l.Line.RequiredDate ?? s.Today), firstMonth) == m)
            .Sum(l => l.Tc ?? 0))).ToList();

        var required = rows.Where(r => r.NetRequirement > 0).ToList();
        return new MrpDashboard(
            s.Period.Info,
            horizon.Select(PeriodResolver.MonthLabel).ToList(),
            required.Count,
            required.Count(r => r.OrderByDate is { } d && d <= soon),
            required.Count(r => r.DaysLate > 0),
            Mapping.R(required.Sum(r => r.RecommendedTc ?? 0)),
            user.Has(Contracts.Security.Permissions.FinanceView) ? Mapping.R(required.Sum(r => r.RecommendedValue ?? 0)) : null,
            required.GroupBy(r => r.Category).Select(g => new ChartPoint(g.Key, Mapping.R(g.Sum(r => r.RecommendedTc ?? 0)), g.Key))
                .Where(c => c.Value > 0).OrderByDescending(c => c.Value).ToList(),
            forecastTc, incomingTc, s.Settings.General.Currency);
    }

    public async Task<PagedResult<MrpRow>> GetRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, sort, desc);
    }

    public async Task<IReadOnlyList<MrpRow>> GetAllRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, sort, desc).ToList();
    }

    private async Task<(IEnumerable<MrpRow>, string, bool)> RowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        IEnumerable<MrpRow> rows = Build(s, user.Has(Contracts.Security.Permissions.FinanceView));
        var soon = s.Today.AddDays(7);
        rows = q.View?.ToLowerInvariant() switch
        {
            "all" => rows,
            "now" => rows.Where(r => r.NetRequirement > 0 && r.OrderByDate is { } d && d <= soon),
            "late" => rows.Where(r => r.DaysLate > 0),
            _ => rows.Where(r => r.NetRequirement > 0),
        };
        return (rows, "OrderByDate", false);
    }

    private static List<int> Horizon(AnalyticsSnapshot s) =>
        Enumerable.Range(1, Math.Max(1, s.Settings.Forecast.HorizonMonths)).Select(i => DateKeys.AddMonths(s.Period.AsOfMonthKey, i)).ToList();

    internal static List<MrpRow> Build(AnalyticsSnapshot s, bool finance)
    {
        var horizon = Horizon(s);
        var horizonEnd = DateKeys.MonthEnd(DateKeys.FromKey(horizon[^1]));
        var rows = new List<MrpRow>();
        foreach (var pos in s.Positions.Values)
        {
            var p = pos.Product;
            var fn = s.DemandFn(p.Id);
            var forecast = horizon.Select(m => Math.Max(0, fn(m))).ToList();
            if (forecast.Sum() <= 0 && pos.Closing <= 0) continue;

            var purchased = p.MaterialType != MaterialType.FinishedGood;
            var lead = purchased ? LeadTimes.ProductLeadDays(p, s.Settings.Supply) : null;
            double? multiple = purchased && pos.UnitsPerTc is { } u && forecast.Average() >= u / 2 ? u : null;
            var r = MrpCalculator.Compute(pos.Closing, pos.OpenQty, forecast, pos.SafetyStock, multiple, lead, pos.StockoutDate, horizonEnd, s.Today);

            var risk = r.DaysLate > 0 ? Labels.Of(ImpactLevel.Critical)
                : r.NetRequirement > 0 && pos.StockoutDate is { } so && so <= horizonEnd ? Labels.Of(ImpactLevel.High)
                : r.NetRequirement > 0 ? Labels.Of(ImpactLevel.Medium)
                : "OK";
            rows.Add(new MrpRow(p.CArtSap, p.Description, p.CategoryName, Labels.Of(p.MaterialType), p.Unit, p.MainSupplierName,
                Mapping.R(pos.Closing), forecast.Select(Mapping.R).ToList(), Mapping.R(pos.OpenQty - pos.TransitQty), Mapping.R(pos.TransitQty),
                Mapping.R(pos.SafetyStock), Mapping.R(r.ProjectedStock), Mapping.R(pos.CoverageMonths), Labels.Of(pos.Status),
                Mapping.R(r.NetRequirement), Mapping.R(r.RecommendedOrder), Mapping.R(pos.Tc(r.RecommendedOrder)), lead, r.NeedDate, r.OrderByDate, r.DaysLate,
                risk, finance ? Mapping.R(pos.Value(r.RecommendedOrder)) : null));
        }
        return rows;
    }

    private static string Search(MrpRow r) => $"{r.CArtSap} {r.Description} {r.Category} {r.Supplier} {r.MaterialType}";

    private static readonly Dictionary<string, Func<MrpRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CArtSap"] = r => r.CArtSap,
        ["Description"] = r => r.Description,
        ["Category"] = r => r.Category,
        ["OpeningStock"] = r => r.OpeningStock,
        ["OpenOrder"] = r => r.OpenOrder,
        ["InTransit"] = r => r.InTransit,
        ["ProjectedStock"] = r => r.ProjectedStock,
        ["CoverageMonths"] = r => r.CoverageMonths,
        ["NetRequirement"] = r => r.NetRequirement,
        ["RecommendedOrder"] = r => r.RecommendedOrder,
        ["RecommendedTc"] = r => r.RecommendedTc,
        ["OrderByDate"] = r => r.OrderByDate,
        ["NeedDate"] = r => r.NeedDate,
        ["Risk"] = r => Labels.Rank<ImpactLevel>(r.Risk, -1),
    };
}

namespace Broli.SOP.Application.Services;

public sealed class DemandService(IAnalyticsEngine engine)
{
    public async Task<DemandDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var tol = s.Settings.Forecast.OnTrackTolerancePct;
        var period = s.DemandIn(s.Period.MonthKeys).ToList();
        var (unit, conv) = s.AggregationUnit(s.Demand.Select(d => d.ProductId).Distinct());

        double Sum(IEnumerable<DemandPoint> ds, Func<DemandPoint, double> q) => ds.Sum(d => conv(d.ProductId, q(d)) ?? 0);
        var f = Sum(period, d => d.Forecast);
        var a = Sum(period, d => d.Actual);
        var rows = BuildRows(s, period);

        var summary = new DemandSummary(
            Mapping.R(f), Mapping.R(a), Mapping.R(a - f), Mapping.R(KpiMath.VariancePct(f, a)),
            Mapping.R(KpiMath.ForecastAccuracyPct(period.Select(d => (d.Forecast, d.Actual)))),
            Mapping.R(KpiMath.BiasPct(f, a)),
            rows.Count(r => r.Status == Labels.Of(ForecastStatus.OnTrack)),
            rows.Count(r => r.Status == Labels.Of(ForecastStatus.UnderForecast)),
            rows.Count(r => r.Status == Labels.Of(ForecastStatus.OverForecast)));

        var months = s.WindowMonths.Skip(1).ToList();
        var byMonth = s.Demand.GroupBy(d => d.MonthKey).ToDictionary(g => g.Key, g => g.ToList());
        double? M(int m, Func<List<DemandPoint>, double?> fn) => byMonth.TryGetValue(m, out var ds) ? Mapping.R(fn(ds)) : null;

        var idByCode = s.Products.ToDictionary(p => p.CArtSap, p => p.Id);
        var worst = rows.Where(r => r.AccuracyPct.HasValue)
            .OrderByDescending(r => conv(idByCode.GetValueOrDefault(r.CArtSap), r.Actual) ?? 0)
            .Take(15)
            .OrderBy(r => r.AccuracyPct)
            .Select(r => new ChartPoint($"{r.CArtSap} {Short(r.Description)}", r.AccuracyPct, r.CArtSap))
            .ToList();

        var biasByFamily = period
            .GroupBy(d => s.Positions.TryGetValue(d.ProductId, out var p) ? (p.Product.CategoryCode, p.Product.CategoryName) : ("?", "Unknown"))
            .Select(g => new ChartPoint(g.Key.Item2, Mapping.R(KpiMath.BiasPct(Sum(g, d => d.Forecast), Sum(g, d => d.Actual))), g.Key.Item1))
            .Where(c => c.Value.HasValue)
            .OrderByDescending(c => Math.Abs(c.Value!.Value))
            .ToList();

        return new DemandDashboard(
            s.Period.Info, summary, unit,
            months.Select(PeriodResolver.MonthLabel).ToList(),
            months.Select(m => M(m, ds => Sum(ds, d => d.Forecast))).ToList(),
            months.Select(m => M(m, ds => Sum(ds, d => d.Actual))).ToList(),
            months.Select(m => M(m, ds => KpiMath.ForecastAccuracyPct(ds.Select(d => (d.Forecast, d.Actual))))).ToList(),
            worst, biasByFamily, tol, s.Settings.Forecast.AccuracyTargetPct, months.ToList());
    }

    public async Task<PagedResult<DemandRow>> GetRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        return TableHelper.Page(ApplyView(BuildRows(s, s.DemandIn(s.Period.MonthKeys).ToList()), q.View), q, SortKeys,
            r => $"{r.CArtSap} {r.Description} {r.Category} {r.Brand}", "Actual", true);
    }

    public async Task<IReadOnlyList<DemandRow>> GetAllRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var rows = ApplyView(BuildRows(s, s.DemandIn(s.Period.MonthKeys).ToList()), q.View);
        return TableHelper.Sort(TableHelper.Filter(rows, q, r => $"{r.CArtSap} {r.Description} {r.Category} {r.Brand}"), q, SortKeys, "Actual", true).ToList();
    }

    private static IEnumerable<DemandRow> ApplyView(IEnumerable<DemandRow> rows, string? view) => view?.ToLowerInvariant() switch
    {
        "under" => rows.Where(r => r.Status == Labels.Of(ForecastStatus.UnderForecast)),
        "over" => rows.Where(r => r.Status == Labels.Of(ForecastStatus.OverForecast)),
        "ontrack" => rows.Where(r => r.Status == Labels.Of(ForecastStatus.OnTrack)),
        _ => rows,
    };

    private static readonly Dictionary<string, Func<DemandRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CArtSap"] = r => r.CArtSap,
        ["Description"] = r => r.Description,
        ["Category"] = r => r.Category,
        ["Brand"] = r => r.Brand,
        ["Forecast"] = r => r.Forecast,
        ["Actual"] = r => r.Actual,
        ["Variance"] = r => r.Variance,
        ["VariancePct"] = r => r.VariancePct,
        ["AccuracyPct"] = r => r.AccuracyPct,
        ["BiasPct"] = r => r.BiasPct,
        ["Status"] = r => r.Status,
    };

    private static List<DemandRow> BuildRows(AnalyticsSnapshot s, IReadOnlyList<DemandPoint> period)
    {
        var tol = s.Settings.Forecast.OnTrackTolerancePct;
        return period.GroupBy(d => d.ProductId)
            .Where(g => s.Positions.ContainsKey(g.Key))
            .Select(g =>
            {
                var p = s.Positions[g.Key].Product;
                var f = g.Sum(d => d.Forecast);
                var a = g.Sum(d => d.Actual);
                return new DemandRow(p.CArtSap, p.Description, p.CategoryName, p.Brand, p.Unit,
                    Mapping.R(f), Mapping.R(a), Mapping.R(a - f), Mapping.R(KpiMath.VariancePct(f, a)),
                    Mapping.R(KpiMath.ForecastAccuracyPct(g.Select(d => (d.Forecast, d.Actual)))),
                    Mapping.R(KpiMath.BiasPct(f, a)),
                    Labels.Of(KpiMath.ClassifyForecast(f, a, tol)));
            })
            .ToList();
    }

    private static string Short(string text) => text.Length <= 22 ? text : text[..21] + "…";
}

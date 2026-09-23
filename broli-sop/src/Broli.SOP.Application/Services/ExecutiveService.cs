namespace Broli.SOP.Application.Services;

public sealed class ExecutiveService(IAnalyticsEngine engine, ICurrentUser user)
{
    public async Task<ExecutiveDashboard> GetAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var set = s.Settings;
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var pos = s.Positions.Values.ToList();
        var prev = s.PreviousPositions.Values.ToList();

        double SumTc(IEnumerable<ProductPosition> ps, Func<ProductPosition, double> q) => ps.Sum(p => p.Tc(q(p)) ?? 0);
        double? Coverage(IEnumerable<ProductPosition> ps)
        {
            var withDemand = ps.Where(p => p.AvgConsumption > 0 && p.UnitsPerTc.HasValue).ToList();
            return KpiMath.SafeDivide(SumTc(withDemand, p => p.Available), SumTc(withDemand, p => p.AvgConsumption));
        }

        var totalTc = SumTc(pos, p => p.Closing);
        var prevTc = SumTc(prev, p => p.Closing);
        var coverage = Coverage(pos);
        var prevCoverage = Coverage(prev);
        var atRisk = pos.Count(p => p.AtRisk);
        var prevAtRisk = prev.Count(p => p.AtRisk);
        var atRiskTc = SumTc(pos.Where(p => p.AtRisk), p => p.Closing);
        var stockValue = finance ? pos.Sum(p => p.Value(p.Closing) ?? 0) : (double?)null;

        var lines = s.FilterLines(filter).ToList();
        var open = lines.Where(l => l.IsOpen).ToList();
        var transitTc = open.Where(l => l.Line.Status.IsInTransit()).Sum(l => l.Tc ?? 0);
        var portTc = open.Where(l => l.Line.Status.IsAtPort()).Sum(l => l.Tc ?? 0);
        var lateOpen = open.Count(l => l.Assessment.Level is EtaRiskLevel.SupplyRisk or EtaRiskLevel.Critical);

        var demand = s.DemandIn(s.Period.MonthKeys).ToList();
        var prevDemand = s.DemandIn(s.Period.PreviousMonthKeys).ToList();
        var accuracy = KpiMath.ForecastAccuracyPct(demand.Select(d => (d.Forecast, d.Actual)));
        var prevAccuracy = KpiMath.ForecastAccuracyPct(prevDemand.Select(d => (d.Forecast, d.Actual)));
        var service = KpiMath.ServiceLevelPct(demand.Where(d => d.Ordered.HasValue).Select(d => (d.Ordered!.Value, d.Actual)));
        var prevService = KpiMath.ServiceLevelPct(prevDemand.Where(d => d.Ordered.HasValue).Select(d => (d.Ordered!.Value, d.Actual)));
        var otif = lines.DeliveredIn(s.Period.MonthKeys).OtifPct(set.Supply);
        var prevOtif = lines.DeliveredIn(s.Period.PreviousMonthKeys).OtifPct(set.Supply);

        var (unit, convert) = s.AggregationUnit(demand.Select(d => d.ProductId).Distinct());
        double SumConv(IEnumerable<DemandPoint> ds, Func<DemandPoint, double> q) => ds.Sum(d => convert(d.ProductId, q(d)) ?? 0);
        var fva = KpiMath.VariancePct(SumConv(demand, d => d.Forecast), SumConv(demand, d => d.Actual));
        var prevFva = KpiMath.VariancePct(SumConv(prevDemand, d => d.Forecast), SumConv(prevDemand, d => d.Actual));

        var coverageStatus = CoverageCalculator.Classify(coverage, coverage.HasValue ? 1 : 0, set.Coverage);
        var skuCount = Math.Max(1, pos.Count(p => p.AvgConsumption > 0));

        var kpis = new List<KpiCard>
        {
            Card("TOTAL_STOCK", "Total Stock", totalTc, "number", "TC", prevTc, true, "neutral",
                stockValue is { } v ? $"Value {v:#,0} {set.General.Currency}" : $"{pos.Count(p => p.Closing > 0)} SKUs in stock", "/inventory"),
            Card("COVERAGE", "Stock Coverage", coverage, "months", "months", prevCoverage, true,
                coverageStatus switch
                {
                    CoverageStatus.Critical or CoverageStatus.Risk => "bad",
                    CoverageStatus.Watch or CoverageStatus.Excess => "watch",
                    CoverageStatus.Normal => "good",
                    _ => "neutral",
                },
                $"Basis: {Labels.Of(set.Coverage.Basis)}, {set.Coverage.AverageMonths} months", "/inventory?view=coverage"),
            Card("STOCK_AT_RISK", "Stock at Risk", atRisk, "integer", "SKUs", prevAtRisk, false,
                atRisk == 0 ? "good" : atRisk * 10 >= skuCount ? "bad" : "watch",
                $"{atRiskTc:#,0.#} TC below {set.Coverage.RiskBelowMonths:0.#} months of cover", "/inventory?view=at-risk"),
            Card("OPEN_ORDERS", "Open Orders", open.Count, "integer", "PO lines", null, true,
                lateOpen > 0 ? "watch" : "neutral", $"{open.Sum(l => l.Tc ?? 0):#,0.#} TC · {lateOpen} late", "/supply?view=open"),
            Card("TC_TRANSIT", "TC in Transit", transitTc, "number", "TC", null, true, "neutral",
                $"{open.Count(l => l.Line.Status.IsInTransit())} shipments on the way", "/supply?view=transit"),
            Card("TC_PORT", "TC at Port", portTc, "number", "TC", null, false,
                open.Any(l => l.Line.Status.IsAtPort() && l.Assessment.Level >= EtaRiskLevel.SupplyRisk) ? "watch" : "neutral",
                $"{open.Count(l => l.Line.Status.IsAtPort())} shipments at port / customs", "/supply?view=port"),
            Card("FORECAST_ACCURACY", "Forecast Accuracy", accuracy, "percent", "%", prevAccuracy, true,
                Traffic(accuracy, set.Forecast.AccuracyTargetPct, 10), $"Target {set.Forecast.AccuracyTargetPct:0}%", "/demand"),
            Card("SERVICE_LEVEL", "Service Level", service, "percent", "%", prevService, true,
                Traffic(service, set.Forecast.ServiceLevelTargetPct, 5), $"Target {set.Forecast.ServiceLevelTargetPct:0}%", "/demand?view=under"),
            Card("OTIF", "OTIF", otif, "percent", "%", prevOtif, true,
                Traffic(otif, set.Supply.OtifTargetPct, 10), $"Target {set.Supply.OtifTargetPct:0}% · supplier deliveries", "/supply?view=delivered"),
            Card("FVA", "Forecast vs Actual", fva, "signedPercent", "%", prevFva, false,
                fva is null ? "neutral" : Math.Abs(fva.Value) <= set.Forecast.OnTrackTolerancePct ? "good"
                    : Math.Abs(fva.Value) <= 2 * set.Forecast.OnTrackTolerancePct ? "watch" : "bad",
                fva is null ? "No demand in period" : fva > 0 ? "Demand above forecast" : "Demand below forecast", "/demand"),
        };
        // "Forecast vs Actual" is better when closer to zero: compare absolute values for the trend arrow.
        kpis[^1] = kpis[^1] with { ChangePct = fva is { } a && prevFva is { } b ? KpiMath.ChangePct(Math.Abs(a), Math.Abs(b)) : null };

        var trendMonths = s.WindowMonths.Skip(1).ToList();
        var byMonth = s.Demand.GroupBy(d => d.MonthKey).ToDictionary(g => g.Key, g => g.ToList());
        var (trendUnit, trendConv) = s.AggregationUnit(s.Demand.Select(d => d.ProductId).Distinct());
        ChartSeries Trend(string name, Func<DemandPoint, double> q) => new(name, trendMonths
            .Select(m => new ChartPoint(PeriodResolver.MonthLabel(m),
                byMonth.TryGetValue(m, out var ds) ? Mapping.R(ds.Sum(d => trendConv(d.ProductId, q(d)) ?? 0)) : null, m.ToString()))
            .ToList());

        return new ExecutiveDashboard(
            s.Period.Info,
            kpis,
            StockByCategory(pos),
            trendUnit,
            Trend("Forecast", d => d.Forecast),
            Trend("Actual", d => d.Actual),
            CoverageDistribution(pos),
            pos.Where(p => p.AtRisk).OrderBy(p => p.CoverageMonths ?? 0).ThenByDescending(p => p.AvgConsumption)
                .Take(8).Select(p => p.ToRow(finance)).ToList(),
            open.Where(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk)
                .OrderByDescending(l => l.Assessment.Level).ThenBy(l => l.Line.Eta).Take(8).Select(l => l.ToRow()).ToList(),
            s.Products.Any(p => p.IsDemo),
            set.General.Currency);

        KpiCard Card(string code, string title, double? value, string format, string? unitLabel, double? previous, bool higherIsBetter,
            string status, string? subtitle, string drill) =>
            new(code, title, Mapping.R(value), format, unitLabel, Mapping.R(previous), KpiMath.ChangePct(value, previous), higherIsBetter,
                value is null ? "neutral" : status, subtitle, drill);
    }

    private static string Traffic(double? value, double target, double watchBand) =>
        value is not { } v ? "neutral" : v >= target ? "good" : v >= target - watchBand ? "watch" : "bad";

    internal static IReadOnlyList<ChartPoint> StockByCategory(IEnumerable<ProductPosition> pos) =>
        pos.GroupBy(p => (p.Product.CategoryCode, p.Product.CategoryName))
            .Select(g => new ChartPoint(g.Key.CategoryName, Mapping.R(g.Sum(p => p.Tc(p.Closing) ?? 0)), g.Key.CategoryCode))
            .Where(c => c.Value > 0)
            .OrderByDescending(c => c.Value)
            .ToList();

    internal static IReadOnlyList<ChartPoint> CoverageDistribution(IEnumerable<ProductPosition> pos)
    {
        var counts = pos.GroupBy(p => p.Status).ToDictionary(g => g.Key, g => g.Count());
        return new[] { CoverageStatus.Critical, CoverageStatus.Risk, CoverageStatus.Watch, CoverageStatus.Normal, CoverageStatus.Excess, CoverageStatus.NoDemand }
            .Select(st => new ChartPoint(Labels.Of(st), counts.GetValueOrDefault(st), st.ToString()))
            .ToList();
    }
}

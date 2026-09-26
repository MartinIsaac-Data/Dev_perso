namespace Broli.SOP.Application.Calculations;

public record MrpResult(
    double TotalForecast,
    double ProjectedStock,
    double NetRequirement,
    double RecommendedOrder,
    DateOnly? NeedDate,
    DateOnly? OrderByDate,
    int? DaysLate);

/// <summary>
/// Net requirement over the horizon:
/// <c>max(0, Σ forecast(M+1…M+H) + safety stock − (stock + open orders + in transit))</c>,
/// rounded up to the ordering multiple (a container for purchased goods).
/// The order-by date is the need date minus the lead time; before today means the order is already late.
/// </summary>
public static class MrpCalculator
{
    public static MrpResult Compute(
        double stock,
        double openSupply,
        IReadOnlyList<double> forecast,
        double safetyStock,
        double? orderMultiple,
        int? leadTimeDays,
        DateOnly? projectedStockout,
        DateOnly horizonEnd,
        DateOnly today)
    {
        var total = forecast.Sum(f => Math.Max(0, f));
        var available = Math.Max(0, stock) + Math.Max(0, openSupply);
        var projected = available - total;
        var net = Math.Max(0, total + Math.Max(0, safetyStock) - available);
        var recommended = KpiMath.RoundUpToMultiple(net, orderMultiple);

        // Needed when stock (with the supply already ordered) runs out; a requirement with no stockout in
        // the horizon is driven by safety stock and is needed by the end of the horizon.
        DateOnly? need = projectedStockout ?? (net > 0 ? horizonEnd : null);
        DateOnly? orderBy = need is { } n && leadTimeDays is { } lt ? n.AddDays(-lt) : need;
        int? late = orderBy is { } ob && ob < today ? today.DayNumber - ob.DayNumber : null;
        return new MrpResult(total, projected, net, recommended, need, orderBy, late);
    }
}

public static class MaterialFlags
{
    public const string Shortage = "Pénurie";
    public const string StockoutRisk = "Risque de rupture";
    public const string Excess = "Excédent";
    public const string SlowMoving = "Rotation lente";
    public const string LateSupply = "Appro en retard";

    public static readonly string[] All = [Shortage, StockoutRisk, LateSupply, Excess, SlowMoving];

    /// <summary>
    /// Automatic flags. Shortage = critical coverage; stockout risk = risk band, or a projected stockout before
    /// <paramref name="alertDate"/> (the date by which a new replenishment could arrive);
    /// excess = above the excess band; slow moving = stock on hand but consumption over the last N months below 5 % of it;
    /// late supply = an open line assessed Supply Risk or Critical.
    /// </summary>
    public static IReadOnlyList<string> Compute(
        ProductPosition pos,
        double recentConsumption,
        bool hasLateSupply,
        DateOnly alertDate)
    {
        var flags = new List<string>();
        if (pos.Status == CoverageStatus.Critical) flags.Add(Shortage);
        else if (pos.Status == CoverageStatus.Risk || pos.StockoutDate is { } so && so <= alertDate) flags.Add(StockoutRisk);
        if (hasLateSupply) flags.Add(LateSupply);
        if (pos.Status == CoverageStatus.Excess) flags.Add(Excess);
        if (pos.Closing > 0 && recentConsumption <= pos.Closing * 0.05) flags.Add(SlowMoving);
        return flags;
    }

    /// <summary>A replenishment ordered today arrives after the lead time; never earlier than the Risk band.</summary>
    public static DateOnly AlertDate(DateOnly asOf, int? leadTimeDays, CoverageSettings s) =>
        asOf.AddDays(Math.Max(leadTimeDays ?? 0, (int)Math.Round(s.RiskBelowMonths * 30.4)));

    public static string Risk(IReadOnlyList<string> flags) =>
        flags.Contains(Shortage) ? Labels.Of(ImpactLevel.Critical)
        : flags.Contains(StockoutRisk) || flags.Contains(LateSupply) ? Labels.Of(ImpactLevel.High)
        : flags.Contains(Excess) || flags.Contains(SlowMoving) ? Labels.Of(ImpactLevel.Medium)
        : "OK";
}

public record SupplierScore(
    int Orders,
    int Delivered,
    double? OnTimePct,
    double? AvgDelayDays,
    int PartialDeliveries,
    int OpenOrders,
    double InTransitTc,
    double? AvgTransitDays,
    int LateOpen,
    int CriticalOpen,
    string Risk);

public static class SupplierScoring
{
    /// <summary>Scores one supplier from its lines (delivered in the window + open).</summary>
    public static SupplierScore Score(IReadOnlyList<AssessedLine> lines, SupplySettings s)
    {
        var delivered = lines.Where(l => l.Line.Status == SupplyStatus.Delivered && l.Line.ActualArrival.HasValue).ToList();
        var open = lines.Where(l => l.IsOpen).ToList();
        var onTime = delivered.Count(l => l.Line.ActualArrival!.Value <= (l.Line.RequiredDate ?? l.Line.Eta ?? l.Line.ActualArrival.Value).AddDays(s.OnTimeToleranceDays));
        var delays = delivered.Select(l => l.Assessment.DelayDays).OfType<int>().ToList();
        var partial = delivered.Count(l => (l.Line.DeliveredQty ?? l.Line.Quantity) < l.Line.Quantity * s.InFullTolerancePct / 100.0);
        var transit = lines.Select(l => l.TransitDays).OfType<int>().ToList();
        var late = open.Count(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk);
        var critical = open.Count(l => l.Assessment.Level == EtaRiskLevel.Critical);
        var otd = delivered.Count == 0 ? null : KpiMath.Pct(onTime, delivered.Count);

        var risk = critical > 0 ? Labels.Of(ImpactLevel.Critical)
            : otd is { } o && o < s.SupplierOnTimeAlertPct || late > 0 ? Labels.Of(ImpactLevel.High)
            : otd is { } o2 && o2 < s.OtifTargetPct ? Labels.Of(ImpactLevel.Medium)
            : "OK";

        return new SupplierScore(lines.Count(l => l.Line.Status != SupplyStatus.Cancelled), delivered.Count, otd,
            delays.Count == 0 ? null : delays.Average(), partial, open.Count,
            open.Where(l => l.Line.Status.IsInTransit()).Sum(l => l.Tc ?? 0),
            transit.Count == 0 ? null : transit.Average(), late, critical, risk);
    }
}

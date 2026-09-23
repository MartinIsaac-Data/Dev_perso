using Broli.SOP.Contracts.Settings;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Application.Calculations;

/// <summary>
/// Coverage = available stock / average monthly consumption. The consumption basis,
/// the averaging window, what counts as "available" and the bands all come from
/// <see cref="CoverageSettings"/> — nothing here is hard-coded.
/// </summary>
public static class CoverageCalculator
{
    /// <param name="history">Actual monthly consumption, most recent last (already limited to the averaging window).</param>
    /// <param name="forecast">Forecast for the upcoming months (already limited to the averaging window).</param>
    public static double AverageMonthlyConsumption(ConsumptionBasis basis, IReadOnlyList<double> history, IReadOnlyList<double> forecast)
    {
        var hist = history.Count > 0 ? history.Average() : (double?)null;
        var fc = forecast.Count > 0 ? forecast.Average() : (double?)null;
        var avg = basis switch
        {
            ConsumptionBasis.Forecast => fc ?? hist ?? 0,
            ConsumptionBasis.History => hist ?? fc ?? 0,
            ConsumptionBasis.MaxOfBoth => Math.Max(hist ?? 0, fc ?? 0),
            _ => fc ?? hist ?? 0,
        };
        return KpiMath.Finite(avg) is { } a && a > 0 ? a : 0;
    }

    public static double AvailableStock(double onHand, double inTransit, double openOrders, CoverageSettings settings)
    {
        var available = Math.Max(0, onHand);
        if (settings.IncludeOpenOrders) available += Math.Max(0, openOrders); // open orders include transit
        else if (settings.IncludeInTransit) available += Math.Max(0, inTransit);
        return available;
    }

    /// <summary>Months of cover, or null when there is no consumption to cover.</summary>
    public static double? CoverageMonths(double available, double averageMonthlyConsumption) =>
        averageMonthlyConsumption <= 0 ? null : KpiMath.SafeDivide(Math.Max(0, available), averageMonthlyConsumption);

    public static CoverageStatus Classify(double? coverageMonths, double averageMonthlyConsumption, CoverageSettings s)
    {
        if (averageMonthlyConsumption <= 0 || coverageMonths is null) return CoverageStatus.NoDemand;
        var c = coverageMonths.Value;
        if (c < s.CriticalBelowMonths) return CoverageStatus.Critical;
        if (c < s.RiskBelowMonths) return CoverageStatus.Risk;
        if (c < s.WatchBelowMonths) return CoverageStatus.Watch;
        if (c > s.ExcessAboveMonths) return CoverageStatus.Excess;
        return CoverageStatus.Normal;
    }

    public static double SafetyStock(double? explicitQty, string categoryCode, double averageMonthlyConsumption, SafetyStockSettings s)
    {
        if (explicitQty is { } q && q >= 0) return q;
        var months = s.MonthsByCategory.TryGetValue(categoryCode, out var m) ? m : s.DefaultMonths;
        return Math.Max(0, months * averageMonthlyConsumption);
    }

    /// <summary>Stock above the excess threshold. With no consumption at all, the whole stock is excess.</summary>
    public static double ExcessStock(double available, double averageMonthlyConsumption, CoverageSettings s)
    {
        if (available <= 0) return 0;
        if (averageMonthlyConsumption <= 0) return available;
        return Math.Max(0, available - s.ExcessAboveMonths * averageMonthlyConsumption);
    }

    public static bool IsAtRisk(CoverageStatus status) => status is CoverageStatus.Critical or CoverageStatus.Risk;
}

using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Application.Calculations;

/// <summary>
/// Core KPI formulas. Every result is either a finite number or null — callers never
/// have to guard against NaN or Infinity, and the UI renders null as "n/a".
/// </summary>
public static class KpiMath
{
    public static double? Finite(double? value) =>
        value is { } v && !double.IsNaN(v) && !double.IsInfinity(v) ? v : null;

    public static double? SafeDivide(double numerator, double denominator) =>
        denominator == 0 ? null : Finite(numerator / denominator);

    public static double? Pct(double numerator, double denominator) =>
        SafeDivide(numerator, denominator) is { } r ? r * 100 : null;

    /// <summary>Relative change vs a previous value, in %. Null when there is no meaningful base.</summary>
    public static double? ChangePct(double? current, double? previous)
    {
        if (current is null || previous is null || previous.Value == 0) return null;
        return Finite((current.Value - previous.Value) / Math.Abs(previous.Value) * 100);
    }

    /// <summary>
    /// Weighted forecast accuracy: 1 − Σ|Actual − Forecast| / ΣActual, floored at 0 %.
    /// Errors are summed at the granularity of the pairs supplied (typically product × month),
    /// so over- and under-forecasts on different products do not cancel out.
    /// </summary>
    public static double? ForecastAccuracyPct(IEnumerable<(double Forecast, double Actual)> pairs)
    {
        double sumActual = 0, sumError = 0;
        foreach (var (f, a) in pairs)
        {
            sumActual += a;
            sumError += Math.Abs(a - f);
        }
        if (sumActual <= 0) return null;
        return Finite(Math.Max(0, 1 - sumError / sumActual) * 100);
    }

    /// <summary>BIAS = (ΣForecast − ΣActual) / ΣActual. Positive = over-forecasting.</summary>
    public static double? BiasPct(double sumForecast, double sumActual) =>
        sumActual <= 0 ? null : Finite((sumForecast - sumActual) / sumActual * 100);

    /// <summary>Variance % = (Actual − Forecast) / Forecast. Positive = demand above forecast.</summary>
    public static double? VariancePct(double forecast, double actual) =>
        forecast == 0 ? null : Finite((actual - forecast) / forecast * 100);

    public static ForecastStatus ClassifyForecast(double forecast, double actual, double tolerancePct)
    {
        if (forecast == 0 && actual == 0) return ForecastStatus.NoData;
        var variance = VariancePct(forecast, actual);
        if (variance is null) return ForecastStatus.UnderForecast; // demand with no forecast at all
        if (Math.Abs(variance.Value) <= tolerancePct) return ForecastStatus.OnTrack;
        return actual > forecast ? ForecastStatus.UnderForecast : ForecastStatus.OverForecast;
    }

    /// <summary>Service level (fill rate) = Σ min(delivered, ordered) / Σ ordered.</summary>
    public static double? ServiceLevelPct(IEnumerable<(double Ordered, double Delivered)> lines)
    {
        double ordered = 0, served = 0;
        foreach (var (o, d) in lines)
        {
            if (o <= 0) continue;
            ordered += o;
            served += Math.Min(Math.Max(d, 0), o);
        }
        return ordered <= 0 ? null : Pct(served, ordered);
    }

    /// <summary>Rounds a quantity up to a whole number of packing units (e.g. containers).</summary>
    public static double RoundUpToMultiple(double quantity, double? multiple)
    {
        if (quantity <= 0) return 0;
        if (multiple is not { } m || m <= 0) return Math.Ceiling(quantity);
        return Math.Ceiling(quantity / m) * m;
    }
}

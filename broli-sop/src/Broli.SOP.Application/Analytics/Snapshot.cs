namespace Broli.SOP.Application.Analytics;

/// <summary>Stock position of one product at a month, with every coverage input and output.</summary>
public record ProductPosition(
    ProductRef Product,
    int MonthKey,
    double Opening,
    double Receipts,
    double Consumption,
    double Closing,
    double Available,
    double AvgConsumption,
    double? CoverageMonths,
    CoverageStatus Status,
    double SafetyStock,
    double Excess,
    bool BelowSafety,
    bool AtRisk,
    double OpenQty,
    double TransitQty,
    DateOnly? NextEta,
    DateOnly? StockoutDate,
    double? UnitsPerTc)
{
    public double? Tc(double quantity) => TcConverter.ToTc(quantity, UnitsPerTc);
    public double? Value(double quantity) => Product.UnitCost is { } c ? KpiMath.Finite(c * quantity) : null;
}

/// <summary>A supply line together with its product and the ETA risk verdict.</summary>
public record AssessedLine(
    SupplyLineData Line,
    ProductRef Product,
    EtaAssessment Assessment,
    DateOnly? StockoutDate,
    double? Tc,
    int? TransitDays)
{
    public bool IsOpen => Line.Status.IsOpen();
    public double OpenQuantity => IsOpen ? Math.Max(0, Line.Quantity - (Line.DeliveredQty ?? 0)) : 0;
}

/// <summary>
/// Everything the dashboards need for one filter, computed once and cached.
/// Services project it into DTOs; nothing in here depends on the UI.
/// </summary>
public sealed class AnalyticsSnapshot
{
    public required ResolvedPeriod Period { get; init; }
    public required SopSettings Settings { get; init; }
    public required DateOnly Today { get; init; }
    public required bool HasData { get; init; }
    public required IReadOnlyList<ProductRef> Products { get; init; }
    public required IReadOnlyDictionary<int, ProductPosition> Positions { get; init; }
    public required IReadOnlyDictionary<int, ProductPosition> PreviousPositions { get; init; }

    /// <summary>13 month keys ending at the as-of month (oldest first).</summary>
    public required IReadOnlyList<int> WindowMonths { get; init; }
    public required IReadOnlyDictionary<(int Product, int Month), double> Stock { get; init; }
    public required IReadOnlyDictionary<(int Product, int Month), double> Receipts { get; init; }
    public required IReadOnlyDictionary<(int Product, int Month), double> Consumption { get; init; }
    public required IReadOnlyDictionary<(int Product, int Month), double> Production { get; init; }

    /// <summary>Demand restricted to the agency filter, covering the trend window, the period and the previous period.</summary>
    public required IReadOnlyList<DemandPoint> Demand { get; init; }
    public required IReadOnlyList<AssessedLine> Lines { get; init; }

    private readonly Dictionary<int, Func<int, double>> _demandFns = new();
    internal Func<int, Func<int, double>>? DemandFnFactory { get; init; }

    /// <summary>Monthly demand used for projections: forecast when present, else the average consumption.</summary>
    public Func<int, double> DemandFn(int productId)
    {
        lock (_demandFns)
        {
            if (!_demandFns.TryGetValue(productId, out var fn))
                _demandFns[productId] = fn = DemandFnFactory?.Invoke(productId) ?? (_ => 0);
            return fn;
        }
    }

    public IEnumerable<AssessedLine> OpenLines => Lines.Where(l => l.IsOpen);
}

namespace Broli.SOP.Contracts.Dtos;

public record ExecutiveDashboard(
    PeriodInfo Period,
    IReadOnlyList<KpiCard> Kpis,
    IReadOnlyList<ChartPoint> StockByCategoryTc,
    string DemandUnit,
    ChartSeries ForecastTrend,
    ChartSeries ActualTrend,
    IReadOnlyList<ChartPoint> CoverageDistribution,
    IReadOnlyList<InventoryRow> TopRisks,
    IReadOnlyList<SupplyRow> LateSupply,
    bool IsDemoData,
    string Currency);

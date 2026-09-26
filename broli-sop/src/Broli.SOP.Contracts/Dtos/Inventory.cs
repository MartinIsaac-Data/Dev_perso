namespace Broli.SOP.Contracts.Dtos;

/// <summary>Stock position of one product at the as-of month. Quantities in the product's base unit.</summary>
public record InventoryRow(
    string CArtSap,
    string Description,
    string Category,
    string? Brand,
    string MaterialType,
    string Unit,
    double OpeningStock,
    double Receipts,
    double Consumption,
    double ClosingStock,
    double? ClosingTc,
    double SafetyStock,
    double AvgMonthlyConsumption,
    double? CoverageMonths,
    string CoverageStatus,
    double ExcessStock,
    bool BelowSafety,
    bool AtRisk,
    double OpenSupplyQty,
    double InTransitQty,
    DateOnly? NextEta,
    DateOnly? StockoutDate,
    double? StockValue);

/// <summary>Aggregates are in TC (containers) because base units differ across products.</summary>
public record InventorySummary(
    double OpeningTc,
    double ReceiptsTc,
    double ConsumptionTc,
    double ClosingTc,
    double? CoverageMonths,
    double SafetyStockTc,
    double ExcessTc,
    int SkuCount,
    int SkusAtRisk,
    int SkusBelowSafety,
    int SkusExcess,
    double? StockValue,
    double? ExcessValue);

public record InventoryDashboard(
    PeriodInfo Period,
    InventorySummary Summary,
    IReadOnlyList<string> Months,
    IReadOnlyList<double?> OpeningTc,
    IReadOnlyList<double?> ReceiptsTc,
    IReadOnlyList<double?> ConsumptionTc,
    IReadOnlyList<double?> ClosingTc,
    IReadOnlyList<ChartPoint> CoverageDistribution,
    IReadOnlyList<ChartPoint> StockByCategoryTc,
    string CoverageBasis,
    int CoverageAverageMonths,
    string Currency);

namespace Broli.SOP.Contracts.Dtos;

public record ProductInfoDto(
    string CArtSap,
    string Description,
    string Category,
    string? Brand,
    string MaterialType,
    string Unit,
    string? MainSupplier,
    string? Format,
    string? Color,
    double? QtyPerTc,
    double? UnitCost,
    bool IsDemo);

/// <summary>One projected month: opening + incoming − forecast = closing.</summary>
public record ProjectionMonth(
    string Month,
    double Opening,
    double Forecast,
    double Incoming,
    double Closing,
    double? CoverageMonths,
    string CoverageStatus);

public record RecommendedAction(string Severity, string Title, string Detail, string? Reference);

public record ProductDetail(
    PeriodInfo Period,
    ProductInfoDto Info,
    InventoryRow Position,
    IReadOnlyList<string> HistoryMonths,
    IReadOnlyList<double?> HistoryStock,
    IReadOnlyList<double?> HistoryActual,
    IReadOnlyList<double?> HistoryForecast,
    IReadOnlyList<ProjectionMonth> Projection,
    IReadOnlyList<SupplyRow> OpenOrders,
    IReadOnlyList<RecommendedAction> Actions,
    IReadOnlyList<RiskItemDto> RegisterItems);

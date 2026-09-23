namespace Broli.SOP.Contracts.Dtos;

/// <summary>A risk found automatically by the risk engine from current data.</summary>
public record DetectedRisk(
    string Category,
    string Severity,
    string CArtSap,
    string Product,
    string Title,
    string Detail,
    string SuggestedAction,
    string? Reference,
    DateOnly? DueBy);

public record RiskItemDto(
    int Id,
    string Code,
    string Category,
    bool IsOpportunity,
    string Description,
    string? CArtSap,
    string? Product,
    string? SupplierCode,
    string Impact,
    int Probability,
    int Score,
    string Owner,
    string? Action,
    DateOnly? DueDate,
    string Status,
    bool IsOverdue);

public record RiskItemUpsert(
    string Category,
    bool IsOpportunity,
    string Description,
    string? CArtSap,
    string? SupplierCode,
    string Impact,
    int Probability,
    string Owner,
    string? Action,
    DateOnly? DueDate,
    string Status);

public record RiskDashboard(
    PeriodInfo Period,
    int DetectedCount,
    int CriticalCount,
    int OpenRegisterCount,
    int OverdueActions,
    IReadOnlyList<ChartPoint> DetectedByCategory,
    IReadOnlyList<ChartPoint> RegisterByStatus,
    IReadOnlyList<DetectedRisk> Detected);

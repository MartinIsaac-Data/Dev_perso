namespace Broli.SOP.Contracts.Dtos;

public record SupplyRow(
    long Id,
    string PoNumber,
    string CArtSap,
    string Product,
    string Category,
    string Supplier,
    string SupplierCode,
    string? Country,
    double Quantity,
    string Unit,
    double? Tc,
    DateOnly OrderDate,
    DateOnly? RequiredDate,
    DateOnly? Etd,
    DateOnly? Eta,
    DateOnly? ActualArrival,
    string Status,
    int? DelayDays,
    int? TransitDays,
    DateOnly? StockoutDate,
    string RiskLevel,
    string? RiskReason,
    string? Port,
    string? Booking,
    string? BillOfLading,
    string? CustomsStatus);

public record SupplySummary(
    int OpenLines,
    double OpenTc,
    double InTransitTc,
    double AtPortTc,
    int LateLines,
    int CriticalLines,
    double? OtifPct,
    double? AvgDelayDays,
    double? AvgTransitDays);

public record SupplyDashboard(
    PeriodInfo Period,
    SupplySummary Summary,
    IReadOnlyList<ChartPoint> ByStatus,
    IReadOnlyList<ChartPoint> ArrivalsByWeekTc,
    IReadOnlyList<ChartPoint> RiskLevels);

public record SupplyUpdateRequest(DateOnly? Etd, DateOnly? Eta, DateOnly? ActualArrival, string? Status, string? CustomsStatus);

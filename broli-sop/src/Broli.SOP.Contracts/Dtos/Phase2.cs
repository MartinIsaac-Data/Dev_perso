namespace Broli.SOP.Contracts.Dtos;

// ---------------- MRP ----------------

/// <summary>Net requirement of one product over the forecast horizon (M+1…M+H).</summary>
public record MrpRow(
    string CArtSap,
    string Description,
    string Category,
    string MaterialType,
    string Unit,
    string? Supplier,
    double OpeningStock,
    IReadOnlyList<double> Forecast,
    double OpenOrder,
    double InTransit,
    double SafetyStock,
    double ProjectedStock,
    double? CoverageMonths,
    string CoverageStatus,
    double NetRequirement,
    double RecommendedOrder,
    double? RecommendedTc,
    int? LeadTimeDays,
    DateOnly? NeedDate,
    DateOnly? OrderByDate,
    int? DaysLate,
    string Risk,
    double? RecommendedValue);

public record MrpDashboard(
    PeriodInfo Period,
    IReadOnlyList<string> HorizonMonths,
    int SkusWithRequirement,
    int OrdersToPlaceNow,
    int OrdersLate,
    double RecommendedTc,
    double? RecommendedValue,
    IReadOnlyList<ChartPoint> RequirementByCategoryTc,
    IReadOnlyList<double?> ForecastByMonthTc,
    IReadOnlyList<double?> IncomingByMonthTc,
    string Currency);

// ---------------- Materials (Raw Materials, Films, Finished Goods) ----------------

/// <summary>One item on a materials dashboard, with its automatic flags.</summary>
public record MaterialRow(
    string CArtSap,
    string Description,
    string Category,
    string? Brand,
    string MaterialType,
    string Unit,
    string? Format,
    string? Color,
    string? Supplier,
    string? SupplierCode,
    string? Country,
    double Stock,
    double? StockTc,
    double AvgConsumption,
    double Forecast,
    double Actual,
    double Production,
    double? ServiceLevelPct,
    double? CoverageMonths,
    string CoverageStatus,
    double OpenPo,
    double InTransit,
    DateOnly? NextEta,
    DateOnly? StockoutDate,
    double? UnitCost,
    double? StockValue,
    IReadOnlyList<string> Flags,
    string Risk);

public record FamilySummary(
    string Code,
    string Name,
    int Skus,
    double StockTc,
    double Forecast,
    double Actual,
    double Production,
    double? ServiceLevelPct,
    double? CoverageMonths,
    int AtRisk);

public record MaterialsDashboard(
    PeriodInfo Period,
    string Kind,
    string Title,
    int Skus,
    double StockTc,
    double? StockKg,
    double? CoverageMonths,
    double? ServiceLevelPct,
    double? StockValue,
    double OpenPoTc,
    double InTransitTc,
    IReadOnlyList<ChartPoint> FlagCounts,
    IReadOnlyList<ChartPoint> StockByGroupTc,
    IReadOnlyList<FamilySummary> Families,
    double KgPerTc,
    string Currency);

// ---------------- Transit ----------------

public record TransitRow(
    long Id,
    string PoNumber,
    string Supplier,
    string SupplierCode,
    string CArtSap,
    string Material,
    double Quantity,
    string Unit,
    double? Tc,
    string? Country,
    string? Port,
    string? Booking,
    string? BillOfLading,
    DateOnly? Etd,
    DateOnly? Eta,
    DateOnly? ActualArrival,
    string Status,
    string? CustomsStatus,
    string Clearing,
    DateOnly? EstimatedDelivery,
    int? TransitDays,
    int? StandardTransitDays,
    int? TransitGapDays,
    int? DelayDays,
    string Risk,
    string? RiskReason);

public record TransitLane(string Country, int Shipments, double? AvgActualDays, int? StandardDays, double? GapDays);

public record TransitDashboard(
    PeriodInfo Period,
    int OnTheWater,
    int AtPort,
    int InCustoms,
    double TcArriving14Days,
    double? AvgTransitDays,
    double? AvgGapDays,
    int LateShipments,
    IReadOnlyList<TransitLane> Lanes,
    IReadOnlyList<ChartPoint> ContainersByStatus,
    int PortToWarehouseDays);

// ---------------- Suppliers ----------------

public record SupplierRow(
    string Code,
    string Name,
    string? Country,
    int Orders,
    int Delivered,
    double? OnTimePct,
    double? AvgDelayDays,
    int PartialDeliveries,
    int OpenOrders,
    double InTransitTc,
    double? AvgTransitDays,
    int? StandardTransitDays,
    int LateOpen,
    int CriticalOpen,
    string Risk);

public record SupplierDashboard(
    PeriodInfo Period,
    int Suppliers,
    double? OnTimePct,
    double? AvgDelayDays,
    int OpenOrders,
    double InTransitTc,
    double? AvgTransitDays,
    int PartialDeliveries,
    int SuppliersAtRisk,
    double AlertPct,
    string Window);

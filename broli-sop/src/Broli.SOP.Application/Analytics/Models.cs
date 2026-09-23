using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Application.Analytics;

/// <summary>Product-dimension part of the global filter, as resolved by the repository.</summary>
public record ProductScope(
    IReadOnlyCollection<string> Categories,
    IReadOnlyCollection<string> Products,
    IReadOnlyCollection<string> Brands,
    IReadOnlyCollection<string> Suppliers,
    IReadOnlyCollection<string> Countries,
    IReadOnlyCollection<MaterialType> MaterialTypes)
{
    public static readonly ProductScope All = new([], [], [], [], [], []);
}

public record ProductRef(
    int Id,
    string CArtSap,
    string Description,
    string CategoryCode,
    string CategoryName,
    string? Brand,
    MaterialType MaterialType,
    string Unit,
    double? QtyPerTc,
    double? UnitCost,
    double? SafetyStockQty,
    string? MainSupplierCode,
    string? MainSupplierName,
    string? Format,
    string? Color,
    bool IsDemo,
    int? SupplierLeadDays = null,
    int? SupplierTransitDays = null,
    string? SupplierCountryCode = null,
    string? SupplierCountryName = null,
    int? CountryTransitDays = null);

public readonly record struct MonthlyQty(int ProductId, int MonthKey, double Quantity);

public readonly record struct DemandPoint(int ProductId, int MonthKey, double Forecast, double Actual, double? Ordered);

public record SupplyLineData(
    long Id,
    string PoNumber,
    int ProductId,
    string SupplierCode,
    string SupplierName,
    string? CountryCode,
    string? CountryName,
    double Quantity,
    double? DeliveredQty,
    double? Containers,
    DateOnly OrderDate,
    DateOnly? RequiredDate,
    DateOnly? Etd,
    DateOnly? Eta,
    DateOnly? ActualArrival,
    SupplyStatus Status,
    string? Port,
    string? Booking,
    string? BillOfLading,
    string? CustomsStatus,
    int? DefaultTransitDays,
    int? SupplierTransitDays = null);

/// <summary>Query window for supply lines: all open lines plus lines delivered in [DeliveredFrom, DeliveredTo].</summary>
public record SupplyWindow(DateOnly DeliveredFrom, DateOnly DeliveredTo);

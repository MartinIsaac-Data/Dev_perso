namespace Broli.SOP.Application.Import;

// Typed, validated rows handed to the repository for writing.

public record SupplierImportRow(string Code, string Name, string CountryCode, int? TransitDays, int? ProductionLeadDays);

public record ProductImportRow(
    string CArtSap, string Description, string CategoryCode, MaterialType? NewCategoryMaterialType, MaterialType MaterialType,
    string? Brand, string Unit, double? UnitWeightKg, double? Colisage, double? QtyPerTc, double? UnitCost, double? SafetyStock,
    string? MainSupplierCode, string? Format, string? Color);

public record SalesImportRow(int MonthKey, string CArtSap, string Agency, double Forecast, double Actual, double? Ordered);

public record InventoryImportRow(int DateKey, string CArtSap, string Warehouse, double Stock);

public record SupplyImportRow(
    string PoNumber, string CArtSap, string SupplierCode, double Quantity, string? CountryCode,
    DateOnly OrderDate, DateOnly? RequiredDate, DateOnly? Etd, DateOnly? Eta, DateOnly? ActualArrival,
    SupplyStatus Status, double? DeliveredQty, double? Containers, string? Port, string? Booking, string? BillOfLading, string? CustomsStatus);

public record ForecastImportRow(string CArtSap, int MonthKey, double Forecast);

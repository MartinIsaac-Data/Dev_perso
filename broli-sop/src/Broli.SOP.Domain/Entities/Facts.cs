using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Domain.Entities;

/// <summary>
/// Monthly demand. For finished goods this is sales per agency; for raw materials and
/// packaging it is consumption by the plant (an internal agency). Keyed on the first day of the month.
/// </summary>
public class SalesFact : IDemoTagged
{
    public long Id { get; set; }
    public int DateKey { get; set; }
    public int ProductId { get; set; }
    public Product? Product { get; set; }
    public int AgencyId { get; set; }
    public Agency? Agency { get; set; }
    /// <summary>The forecast that was valid for this month (frozen), used for accuracy.</summary>
    public double ForecastQty { get; set; }
    /// <summary>Delivered / consumed quantity.</summary>
    public double ActualQty { get; set; }
    /// <summary>Customer ordered quantity, when known. Drives service level.</summary>
    public double? OrderedQty { get; set; }
    public int? ImportBatchId { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>Stock snapshot per product and warehouse at a date (month-end for monthly loads).</summary>
public class InventoryFact : IDemoTagged
{
    public long Id { get; set; }
    public int DateKey { get; set; }
    public int ProductId { get; set; }
    public Product? Product { get; set; }
    public int WarehouseId { get; set; }
    public Warehouse? Warehouse { get; set; }
    public double StockQty { get; set; }
    public int? ImportBatchId { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>Forward-looking forecast per product and month (latest version wins).</summary>
public class ForecastFact : IDemoTagged
{
    public long Id { get; set; }
    public int DateKey { get; set; }
    public int ProductId { get; set; }
    public Product? Product { get; set; }
    public double ForecastQty { get; set; }
    public int? ImportBatchId { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>A purchase-order line and its shipment tracking. One line = one shipment in Phase 1.</summary>
public class SupplyLine : IDemoTagged
{
    public long Id { get; set; }
    public string PoNumber { get; set; } = "";
    public int ProductId { get; set; }
    public Product? Product { get; set; }
    public int SupplierId { get; set; }
    public Supplier? Supplier { get; set; }
    public int? OriginCountryId { get; set; }
    public Country? OriginCountry { get; set; }

    public double Quantity { get; set; }
    public double? DeliveredQty { get; set; }
    public double? Containers { get; set; }

    public DateOnly OrderDate { get; set; }
    /// <summary>Date the goods are required in our warehouse.</summary>
    public DateOnly? RequiredDate { get; set; }
    public DateOnly? Etd { get; set; }
    public DateOnly? Eta { get; set; }
    public DateOnly? ActualArrival { get; set; }

    public SupplyStatus Status { get; set; }
    public string? Port { get; set; }
    public string? Booking { get; set; }
    public string? BillOfLading { get; set; }
    public string? CustomsStatus { get; set; }
    public int? ImportBatchId { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>Monthly production output for finished goods.</summary>
public class ProductionFact : IDemoTagged
{
    public long Id { get; set; }
    public int DateKey { get; set; }
    public int ProductId { get; set; }
    public Product? Product { get; set; }
    public double PlannedQty { get; set; }
    public double ProducedQty { get; set; }
    public int? ImportBatchId { get; set; }
    public bool IsDemo { get; set; }
}

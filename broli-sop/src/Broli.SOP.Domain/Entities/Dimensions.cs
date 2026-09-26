using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Domain.Entities;

/// <summary>Anything that can be flagged as demonstration data. DEMO rows are purged when real data arrives.</summary>
public interface IDemoTagged
{
    bool IsDemo { get; set; }
}

public class Country : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    /// <summary>Default sea/road transit time from this origin, in days. Overridable per supplier.</summary>
    public int DefaultTransitDays { get; set; }
    public bool IsDemo { get; set; }
}

public class Supplier : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    public int CountryId { get; set; }
    public Country? Country { get; set; }
    /// <summary>Overrides the country transit time when set.</summary>
    public int? TransitDays { get; set; }
    /// <summary>Typical production / preparation lead time before departure, in days.</summary>
    public int ProductionLeadDays { get; set; }
    public bool IsDemo { get; set; }
}

public class Category : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    public MaterialType MaterialType { get; set; }
    public bool IsDemo { get; set; }
}

public class Brand : IDemoTagged
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public bool IsDemo { get; set; }
}

public class Product : IDemoTagged
{
    public int Id { get; set; }
    /// <summary>SAP article code — the business key used everywhere in Broli.</summary>
    public string CArtSap { get; set; } = "";
    public string Description { get; set; } = "";
    public int CategoryId { get; set; }
    public Category? Category { get; set; }
    public int? BrandId { get; set; }
    public Brand? Brand { get; set; }
    public MaterialType MaterialType { get; set; }
    public int? MainSupplierId { get; set; }
    public Supplier? MainSupplier { get; set; }

    /// <summary>Stock-keeping unit: KG, CTN (carton), ROLL, UNIT…</summary>
    public string BaseUnit { get; set; } = "CTN";
    public double? UnitWeightKg { get; set; }
    /// <summary>Units per carton / packing unit.</summary>
    public double? Colisage { get; set; }
    /// <summary>Base units per 20' container (TC). When null, KG items use the configured default kg/TC.</summary>
    public double? QtyPerTc { get; set; }
    /// <summary>Standard cost per base unit, in the configured currency.</summary>
    public double? UnitCost { get; set; }
    /// <summary>Explicit safety stock in base units. When null, it is derived from configuration.</summary>
    public double? SafetyStockQty { get; set; }

    public string? Format { get; set; }
    public string? Color { get; set; }
    public bool IsActive { get; set; } = true;
    public bool IsDemo { get; set; }
}

public class Agency : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    /// <summary>Internal consumer (the plant) rather than a commercial agency.</summary>
    public bool IsInternal { get; set; }
    public bool IsDemo { get; set; }
}

public class Warehouse : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    public bool IsDemo { get; set; }
}

public class Customer : IDemoTagged
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    public int? AgencyId { get; set; }
    public bool IsDemo { get; set; }
}

/// <summary>Calendar dimension. Key is yyyymmdd so fact tables can be range-filtered without a join.</summary>
public class DateDim
{
    public int DateKey { get; set; }
    public DateOnly Date { get; set; }
    public int Year { get; set; }
    public int Quarter { get; set; }
    public int Month { get; set; }
    public string MonthName { get; set; } = "";
    public int FiscalYear { get; set; }
    public int FiscalPeriod { get; set; }
    public bool IsMonthStart { get; set; }
}

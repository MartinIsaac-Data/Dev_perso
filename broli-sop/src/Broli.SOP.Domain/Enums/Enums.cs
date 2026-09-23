namespace Broli.SOP.Domain.Enums;

/// <summary>What kind of item a product is. Drives units, replenishment mode and page scoping.</summary>
public enum MaterialType
{
    FinishedGood = 1,
    RawMaterial = 2,
    Packaging = 3,
}

/// <summary>Lifecycle of a purchase-order line / shipment.</summary>
public enum SupplyStatus
{
    Planned = 1,
    Confirmed = 2,
    InProduction = 3,
    Ready = 4,
    Shipped = 5,
    AtPort = 6,
    Customs = 7,
    Delivered = 8,
    Delayed = 9,
    Cancelled = 10,
}

/// <summary>Coverage band a product falls into, from configurable thresholds.</summary>
public enum CoverageStatus
{
    NoDemand = 0,
    Critical = 1,
    Risk = 2,
    Watch = 3,
    Normal = 4,
    Excess = 5,
}

public enum ForecastStatus
{
    NoData = 0,
    OnTrack = 1,
    UnderForecast = 2,
    OverForecast = 3,
}

/// <summary>Result of the ETA risk engine for one inbound supply line.</summary>
public enum EtaRiskLevel
{
    None = 0,
    Watch = 1,
    SupplyRisk = 2,
    Critical = 3,
}

public enum RiskCategory
{
    Stockout = 1,
    Overstock = 2,
    SupplyDelay = 3,
    PortDelay = 4,
    Customs = 5,
    ForecastRisk = 6,
    SupplierRisk = 7,
    ProductionRisk = 8,
    DemandIncrease = 9,
    ExcessStock = 10,
}

public enum RiskStatus
{
    Open = 1,
    InProgress = 2,
    Closed = 3,
}

public enum ImpactLevel
{
    Low = 1,
    Medium = 2,
    High = 3,
    Critical = 4,
}

public enum ImportType
{
    ProductMaster = 1,
    SupplierMaster = 2,
    Sales = 3,
    Inventory = 4,
    Supply = 5,
    Forecast = 6,
}

public enum ImportStatus
{
    Validated = 1,
    Committed = 2,
    Rejected = 3,
}

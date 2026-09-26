
namespace Broli.SOP.Contracts.Settings;

/// <summary>Which demand signal feeds the coverage denominator.</summary>
public enum ConsumptionBasis
{
    /// <summary>Average of the next N months of forecast.</summary>
    Forecast = 1,
    /// <summary>Average of the last N months of actual consumption.</summary>
    History = 2,
    /// <summary>The higher of the two — the prudent choice for shortages.</summary>
    MaxOfBoth = 3,
}


public class CoverageSettings
{
    public const string Key = "coverage";

    public ConsumptionBasis Basis { get; set; } = ConsumptionBasis.Forecast;
    /// <summary>Number of months averaged for the consumption denominator.</summary>
    public int AverageMonths { get; set; } = 3;
    /// <summary>Count goods already shipped as available stock.</summary>
    public bool IncludeInTransit { get; set; }
    /// <summary>Count every open order as available stock.</summary>
    public bool IncludeOpenOrders { get; set; }
    public double CriticalBelowMonths { get; set; } = 1;
    public double RiskBelowMonths { get; set; } = 2;
    public double WatchBelowMonths { get; set; } = 3;
    /// <summary>Coverage above this is excess stock.</summary>
    public double ExcessAboveMonths { get; set; } = 6;
    /// <summary>Stock with no movement for this many months is slow moving.</summary>
    public int SlowMovingMonths { get; set; } = 3;
}

public class SafetyStockSettings
{
    public const string Key = "safetyStock";

    /// <summary>Safety stock expressed in months of average consumption (used when a product has no explicit value).</summary>
    public double DefaultMonths { get; set; } = 1;
    public Dictionary<string, double> MonthsByCategory { get; set; } = new();
}

public class ForecastSettings
{
    public const string Key = "forecast";

    /// <summary>|Variance %| within this tolerance counts as "On Track".</summary>
    public double OnTrackTolerancePct { get; set; } = 10;
    /// <summary>Months ahead shown and used for projections.</summary>
    public int HorizonMonths { get; set; } = 4;
    /// <summary>Accuracy target (%) used for traffic lights.</summary>
    public double AccuracyTargetPct { get; set; } = 80;
    /// <summary>Service level (fill rate) target, %.</summary>
    public double ServiceLevelTargetPct { get; set; } = 95;
    /// <summary>Forecast above history by more than this % is flagged as a demand increase.</summary>
    public double DemandIncreaseThresholdPct { get; set; } = 30;
}

public class SupplySettings
{
    public const string Key = "supply";

    /// <summary>An ETA falling within this many days of the required/stockout date is flagged Watch.</summary>
    public int WatchWindowDays { get; set; } = 7;
    /// <summary>Tolerance in days for "on time" delivery (OTIF).</summary>
    public int OnTimeToleranceDays { get; set; } = 2;
    /// <summary>Delivered quantity must be at least this share of ordered quantity for "in full".</summary>
    public double InFullTolerancePct { get; set; } = 95;
    /// <summary>OTIF target, %.</summary>
    public double OtifTargetPct { get; set; } = 90;
    /// <summary>Days from arrival at port to availability in our warehouse (clearing + delivery). Imports only.</summary>
    public int PortToWarehouseDays { get; set; } = 7;
    /// <summary>A supplier below this on-time delivery rate is flagged as a risk, %.</summary>
    public double SupplierOnTimeAlertPct { get; set; } = 75;
    public Dictionary<string, int> TransitDaysByCountry { get; set; } = new();
}

public class TcSettings
{
    public const string Key = "tc";

    /// <summary>Default kilograms per 20' container for KG-managed materials.</summary>
    public double DefaultKgPerTc { get; set; } = 25000;
}

public class GeneralSettings
{
    public const string Key = "general";

    public string Currency { get; set; } = "XAF";
    /// <summary>1 = January. The fiscal year is named after the calendar year in which it ends.</summary>
    public int FiscalYearStartMonth { get; set; } = 1;
    /// <summary>Product-family codes shown on the Films dashboard.</summary>
    public List<string> FilmCategories { get; set; } = ["FILMS"];
    public List<string> Departments { get; set; } =
        ["Direction", "Supply Chain", "Commercial", "Finance", "Production", "Entrepôt", "Logistique", "Informatique"];
}

/// <summary>Automatic alerts: which rules run and who receives them (by permission).</summary>
public class AlertSettings
{
    public const string Key = "alerts";

    public bool StockoutRisk { get; set; } = true;
    public bool EtaDelay { get; set; } = true;
    public bool CoverageBelowThreshold { get; set; } = true;
    public bool OpenPoOverdue { get; set; } = true;
    public bool ActionsOverdue { get; set; } = true;
    public bool RefreshFailures { get; set; } = true;
    /// <summary>The same alert on the same object is not repeated within this many days.</summary>
    public int RepeatAfterDays { get; set; } = 3;
    /// <summary>Send e-mail as well (requires SMTP configuration on the server).</summary>
    public bool SendEmail { get; set; }
}

/// <summary>A consistent snapshot of every business parameter, loaded once per computation.</summary>
public record SopSettings(
    CoverageSettings Coverage,
    SafetyStockSettings SafetyStock,
    ForecastSettings Forecast,
    SupplySettings Supply,
    TcSettings Tc,
    GeneralSettings General,
    AlertSettings? Alerts = null)
{
    public AlertSettings AlertRules => Alerts ?? new AlertSettings();
    public static SopSettings Defaults() => new(new(), new(), new(), new(), new(), new(), new());
}

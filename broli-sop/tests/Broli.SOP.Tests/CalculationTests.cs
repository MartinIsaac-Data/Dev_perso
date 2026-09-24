using Broli.SOP.Application.Calculations;
using Broli.SOP.Contracts.Settings;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Tests;

public class KpiMathTests
{
    [Fact]
    public void Accuracy_is_one_minus_weighted_absolute_error()
    {
        // |110-100| + |80-100| = 30 over actual 190 → 84.21 %
        var acc = KpiMath.ForecastAccuracyPct([(100, 110), (100, 80)]);
        Assert.Equal((1 - 30.0 / 190) * 100, acc!.Value, 9);
    }

    [Fact]
    public void Accuracy_errors_do_not_cancel_between_products()
    {
        // Totals match (200 vs 200) but each product is 50 % off → 50 %, not 100 %.
        Assert.Equal(50, KpiMath.ForecastAccuracyPct([(150, 100), (50, 100)])!.Value, 6);
    }

    [Fact]
    public void Accuracy_is_floored_at_zero_and_null_without_actuals()
    {
        Assert.Equal(0, KpiMath.ForecastAccuracyPct([(1000, 10)]));
        Assert.Null(KpiMath.ForecastAccuracyPct([(100, 0)]));
        Assert.Null(KpiMath.ForecastAccuracyPct([]));
    }

    [Fact]
    public void Bias_is_positive_when_over_forecasting()
    {
        Assert.Equal(25, KpiMath.BiasPct(125, 100));
        Assert.Equal(-20, KpiMath.BiasPct(80, 100));
        Assert.Null(KpiMath.BiasPct(10, 0));
    }

    [Fact]
    public void Variance_pct_is_null_instead_of_infinity()
    {
        Assert.Equal(10, KpiMath.VariancePct(100, 110));
        Assert.Null(KpiMath.VariancePct(0, 50));
    }

    [Theory]
    [InlineData(100, 105, 10, ForecastStatus.OnTrack)]
    [InlineData(100, 90, 10, ForecastStatus.OnTrack)]
    [InlineData(100, 130, 10, ForecastStatus.UnderForecast)]
    [InlineData(100, 60, 10, ForecastStatus.OverForecast)]
    [InlineData(0, 40, 10, ForecastStatus.UnderForecast)]
    [InlineData(0, 0, 10, ForecastStatus.NoData)]
    [InlineData(100, 125, 30, ForecastStatus.OnTrack)]
    public void Forecast_status_uses_the_configured_tolerance(double f, double a, double tol, ForecastStatus expected) =>
        Assert.Equal(expected, KpiMath.ClassifyForecast(f, a, tol));

    [Fact]
    public void Service_level_caps_delivered_at_ordered()
    {
        // 100/100 + 50/100 (over-delivery ignored on line 3) → (100 + 50 + 20) / 220
        var sl = KpiMath.ServiceLevelPct([(100, 100), (100, 50), (20, 30)]);
        Assert.Equal(170.0 / 220 * 100, sl!.Value, 6);
        Assert.Null(KpiMath.ServiceLevelPct([(0, 10)]));
    }

    [Fact]
    public void Nothing_returns_nan_or_infinity()
    {
        Assert.Null(KpiMath.Finite(double.NaN));
        Assert.Null(KpiMath.Finite(double.PositiveInfinity));
        Assert.Null(KpiMath.SafeDivide(1, 0));
        Assert.Null(KpiMath.ChangePct(5, 0));
        Assert.Null(KpiMath.ChangePct(null, 3));
        Assert.Equal(-50, KpiMath.ChangePct(5, 10));
    }

    [Fact]
    public void Round_up_to_container_multiple()
    {
        Assert.Equal(50000, KpiMath.RoundUpToMultiple(25001, 25000));
        Assert.Equal(0, KpiMath.RoundUpToMultiple(-5, 25000));
        Assert.Equal(13, KpiMath.RoundUpToMultiple(12.2, null));
    }
}

public class CoverageCalculatorTests
{
    private static readonly CoverageSettings Default = new();

    [Fact]
    public void Forecast_basis_averages_the_forecast_and_falls_back_to_history()
    {
        Assert.Equal(200, CoverageCalculator.AverageMonthlyConsumption(ConsumptionBasis.Forecast, [100, 100, 100], [150, 250]));
        Assert.Equal(100, CoverageCalculator.AverageMonthlyConsumption(ConsumptionBasis.Forecast, [100, 100, 100], []));
        Assert.Equal(100, CoverageCalculator.AverageMonthlyConsumption(ConsumptionBasis.History, [100, 100, 100], [300]));
        Assert.Equal(300, CoverageCalculator.AverageMonthlyConsumption(ConsumptionBasis.MaxOfBoth, [100, 100, 100], [300]));
        Assert.Equal(0, CoverageCalculator.AverageMonthlyConsumption(ConsumptionBasis.Forecast, [], []));
    }

    [Fact]
    public void Coverage_is_null_without_demand()
    {
        Assert.Equal(2.5, CoverageCalculator.CoverageMonths(250, 100));
        Assert.Null(CoverageCalculator.CoverageMonths(250, 0));
        Assert.Equal(0, CoverageCalculator.CoverageMonths(-40, 100));
    }

    [Theory]
    [InlineData(0.5, CoverageStatus.Critical)]
    [InlineData(1.0, CoverageStatus.Risk)]
    [InlineData(1.99, CoverageStatus.Risk)]
    [InlineData(2.5, CoverageStatus.Watch)]
    [InlineData(3.0, CoverageStatus.Normal)]
    [InlineData(6.0, CoverageStatus.Normal)]
    [InlineData(6.1, CoverageStatus.Excess)]
    public void Default_bands(double months, CoverageStatus expected) =>
        Assert.Equal(expected, CoverageCalculator.Classify(months, 10, Default));

    [Fact]
    public void Bands_follow_configuration()
    {
        var s = new CoverageSettings { CriticalBelowMonths = 0.5, RiskBelowMonths = 1, WatchBelowMonths = 1.5, ExcessAboveMonths = 4 };
        Assert.Equal(CoverageStatus.Watch, CoverageCalculator.Classify(1.2, 10, s));
        Assert.Equal(CoverageStatus.Excess, CoverageCalculator.Classify(4.5, 10, s));
        Assert.Equal(CoverageStatus.NoDemand, CoverageCalculator.Classify(null, 0, s));
    }

    [Fact]
    public void Available_stock_includes_transit_or_open_orders_only_when_configured()
    {
        Assert.Equal(100, CoverageCalculator.AvailableStock(100, 30, 80, new CoverageSettings()));
        Assert.Equal(130, CoverageCalculator.AvailableStock(100, 30, 80, new CoverageSettings { IncludeInTransit = true }));
        Assert.Equal(180, CoverageCalculator.AvailableStock(100, 30, 80, new CoverageSettings { IncludeOpenOrders = true, IncludeInTransit = true }));
    }

    [Fact]
    public void Safety_stock_prefers_product_value_then_category_then_default()
    {
        var s = new SafetyStockSettings { DefaultMonths = 1, MonthsByCategory = new() { ["FILMS"] = 1.5 } };
        Assert.Equal(42, CoverageCalculator.SafetyStock(42, "FILMS", 100, s));
        Assert.Equal(150, CoverageCalculator.SafetyStock(null, "FILMS", 100, s));
        Assert.Equal(100, CoverageCalculator.SafetyStock(null, "OILS", 100, s));
    }

    [Fact]
    public void Excess_is_stock_above_the_threshold_or_all_stock_without_demand()
    {
        Assert.Equal(200, CoverageCalculator.ExcessStock(800, 100, Default));
        Assert.Equal(0, CoverageCalculator.ExcessStock(500, 100, Default));
        Assert.Equal(300, CoverageCalculator.ExcessStock(300, 0, Default));
    }

    [Fact]
    public void Tc_conversion_uses_product_then_default_kg()
    {
        var tc = new TcSettings { DefaultKgPerTc = 25000 };
        Assert.Equal(2400, TcConverter.UnitsPerTc(2400, "CTN", tc));
        Assert.Equal(25000, TcConverter.UnitsPerTc(null, "KG", tc));
        Assert.Null(TcConverter.UnitsPerTc(null, "UNIT", tc));
        Assert.Equal(2, TcConverter.ToTc(50000, 25000));
        Assert.Null(TcConverter.ToTc(10, null));
    }
}

public class StockProjectionTests
{
    private static readonly DateOnly Start = new(2026, 9, 1); // September: 30 days

    [Fact]
    public void Stock_runs_out_at_the_daily_forecast_rate()
    {
        // 300 per month in September = 10/day; 100 in stock → exhausted on day 10.
        var d = StockProjection.FindStockoutDate(100, Start, Start.AddMonths(6), _ => 300, []);
        Assert.Equal(new DateOnly(2026, 9, 10), d);
    }

    [Fact]
    public void An_arrival_before_the_stockout_pushes_it_back()
    {
        var d = StockProjection.FindStockoutDate(100, Start, Start.AddMonths(6), _ => 300, [new Arrival(new DateOnly(2026, 9, 5), 100)]);
        Assert.Equal(new DateOnly(2026, 9, 20), d);
    }

    [Fact]
    public void No_demand_or_enough_stock_means_no_stockout()
    {
        Assert.Null(StockProjection.FindStockoutDate(100, Start, Start.AddMonths(3), _ => 0, []));
        Assert.Null(StockProjection.FindStockoutDate(100000, Start, Start.AddMonths(3), _ => 300, []));
    }

    [Fact]
    public void Zero_stock_with_demand_is_an_immediate_stockout()
    {
        Assert.Equal(Start, StockProjection.FindStockoutDate(0, Start, Start.AddMonths(3), _ => 300, []));
    }

    [Fact]
    public void Monthly_projection_rolls_closing_into_opening()
    {
        var months = StockProjection.ProjectMonthly(500, 20260901, 3, _ => 200, [new Arrival(new DateOnly(2026, 11, 15), 300)]);
        // Oct: 500 − 200; Nov: 300 + 300 arriving − 200; Dec: 400 − 200.
        Assert.Equal([300, 400, 200], months.Select(m => m.Closing));
        Assert.Equal(20261001, months[0].MonthKey);
        Assert.Equal(300, months[1].Incoming);
    }

    [Fact]
    public void Monthly_projection_never_goes_negative()
    {
        var months = StockProjection.ProjectMonthly(100, 20260901, 2, _ => 400, []);
        Assert.All(months, m => Assert.True(m.Closing >= 0));
    }
}

public class EtaRiskEngineTests
{
    private static readonly DateOnly Today = new(2026, 9, 23);

    [Fact]
    public void Eta_after_projected_stockout_is_critical()
    {
        var a = EtaRiskEngine.Assess(SupplyStatus.Shipped, new(2026, 10, 25), new(2026, 10, 3), null, new(2026, 10, 8), Today, 7);
        Assert.Equal(EtaRiskLevel.Critical, a.Level);
        Assert.Equal(22, a.DelayDays);
        Assert.Contains("17 j après la rupture prévue", a.Reason);
    }

    [Fact]
    public void Eta_after_required_date_is_supply_risk()
    {
        var a = EtaRiskEngine.Assess(SupplyStatus.Confirmed, new(2026, 10, 20), new(2026, 10, 15), null, null, Today, 7);
        Assert.Equal(EtaRiskLevel.SupplyRisk, a.Level);
        Assert.Equal(5, a.DelayDays);
    }

    [Fact]
    public void Eta_inside_the_safety_window_is_watch()
    {
        var a = EtaRiskEngine.Assess(SupplyStatus.Shipped, new(2026, 10, 12), new(2026, 10, 15), null, null, Today, 7);
        Assert.Equal(EtaRiskLevel.Watch, a.Level);
    }

    [Fact]
    public void Comfortable_eta_is_ok()
    {
        var a = EtaRiskEngine.Assess(SupplyStatus.Shipped, new(2026, 10, 1), new(2026, 10, 15), null, new(2026, 12, 1), Today, 7);
        Assert.Equal(EtaRiskLevel.None, a.Level);
        Assert.Equal(0, a.DelayDays);
    }

    [Fact]
    public void Passed_eta_without_receipt_is_supply_risk()
    {
        var a = EtaRiskEngine.Assess(SupplyStatus.AtPort, new(2026, 9, 18), null, null, null, Today, 7);
        Assert.Equal(EtaRiskLevel.SupplyRisk, a.Level);
        Assert.Equal(5, a.DelayDays);
    }

    [Fact]
    public void Missing_eta_is_watch_and_closed_lines_carry_no_risk()
    {
        Assert.Equal(EtaRiskLevel.Watch, EtaRiskEngine.Assess(SupplyStatus.Planned, null, null, null, null, Today, 7).Level);
        var delivered = EtaRiskEngine.Assess(SupplyStatus.Delivered, new(2026, 9, 1), new(2026, 9, 1), new(2026, 9, 6), null, Today, 7);
        Assert.Equal(EtaRiskLevel.None, delivered.Level);
        Assert.Equal(5, delivered.DelayDays);
    }
}

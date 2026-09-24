using Broli.SOP.Domain;
using Broli.SOP.Application;
using Broli.SOP.Application.Analytics;
using Broli.SOP.Application.Calculations;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Settings;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Tests;

public class PeriodResolverTests
{
    private static readonly DateOnly Today = new(2026, 9, 23);

    [Fact]
    public void Default_period_is_the_latest_stock_month()
    {
        var p = PeriodResolver.Resolve(new SopFilter(), 20260901, Today);
        Assert.Equal("September 2026", p.Info.Label);
        Assert.Equal(20260901, p.AsOfMonthKey);
        Assert.Equal(Today, p.AsOfDate);
        Assert.Equal([20260801], p.PreviousMonthKeys);
    }

    [Fact]
    public void Multi_month_selection_compares_with_the_preceding_block()
    {
        var p = PeriodResolver.Resolve(new SopFilter { Year = 2026, Months = [7, 8, 9] }, 20260901, Today);
        Assert.Equal("Jul – Sep 2026", p.Info.Label);
        Assert.Equal([20260401, 20260501, 20260601], p.PreviousMonthKeys);
    }

    [Fact]
    public void Future_months_cap_stock_at_the_latest_snapshot()
    {
        var p = PeriodResolver.Resolve(new SopFilter { Year = 2026, Months = [12] }, 20260901, Today);
        Assert.Equal(20260901, p.AsOfMonthKey);
    }

    [Fact]
    public void Past_month_uses_month_end_and_invalid_months_are_ignored()
    {
        var p = PeriodResolver.Resolve(new SopFilter { Year = 2026, Months = [3, 13, 0] }, 20260901, Today);
        Assert.Equal([3], p.Info.Months);
        Assert.Equal(new DateOnly(2026, 3, 31), p.AsOfDate);
    }
}

public class ActionAdvisorTests
{
    private static ProductRef Film => new(1, "300154", "FILM RAHMA MACARONI 500G", "FILMS", "Films", "Rahma", MaterialType.Packaging, "KG",
        18000, 2600, null, "S01", "Anatolia Films", "500g", "Green", false);

    private static ProductPosition Position(double closing, double avg, CoverageStatus status, double open, DateOnly? stockout) =>
        new(Film, 20260901, closing, 0, avg, closing, closing, avg, avg > 0 ? closing / avg : null, status, avg, 0, closing < avg,
            CoverageCalculator.IsAtRisk(status), open, open, null, stockout, 18000);

    [Fact]
    public void Critical_line_is_expedited_and_shortfall_is_ordered()
    {
        var pos = Position(2500, 5400, CoverageStatus.Critical, 11700, new DateOnly(2026, 10, 8));
        var line = new AssessedLine(
            new SupplyLineData(1, "45000232", 1, "S01", "Anatolia Films", "TR", "Turkey", 11700, null, 1, new(2026, 8, 19), new(2026, 10, 3),
                new(2026, 9, 13), new(2026, 10, 25), null, SupplyStatus.Shipped, "Douala", null, null, null, 30),
            Film, new EtaAssessment(EtaRiskLevel.Critical, "ETA 25/10 is 17 d after projected stockout 08/10", 22), new DateOnly(2026, 10, 8), 1, 42);

        var actions = ActionAdvisor.Advise(pos, [line], SopSettings.Defaults(), new DateOnly(2026, 9, 23));

        Assert.Equal("critical", actions[0].Severity);
        Assert.StartsWith("Expedite PO 45000232", actions[0].Title);
        Assert.Contains(actions, a => a.Title.StartsWith("Place a purchase order"));
    }

    [Fact]
    public void Healthy_product_needs_no_action()
    {
        var pos = Position(20000, 5000, CoverageStatus.Normal, 0, null);
        var actions = ActionAdvisor.Advise(pos, [], SopSettings.Defaults(), new DateOnly(2026, 9, 23));
        Assert.Single(actions);
        Assert.Equal("info", actions[0].Severity);
    }

    [Fact]
    public void Labels_round_trip()
    {
        Assert.Equal("In Production", Labels.Of(SupplyStatus.InProduction));
        Assert.True(Labels.TryParse<SupplyStatus>("at port", out var s));
        Assert.Equal(SupplyStatus.AtPort, s);
        Assert.False(Labels.TryParse<SupplyStatus>("teleported", out _));
    }
}

public class BaseWindowTests
{
    private static readonly DateOnly Today = new(2026, 9, 23);

    [Theory]
    [InlineData(6)]
    [InlineData(12)]
    public void Every_period_of_a_year_shares_the_yearly_window(int horizon)
    {
        var yearly = AnalyticsEngine.BaseWindow.ForYear(20260901, horizon);
        var filters = Enumerable.Range(1, 12).Select(m => new SopFilter { Year = 2026, Months = [m] })
            .Append(new SopFilter())
            .Append(new SopFilter { Year = 2026 })
            .Append(new SopFilter { Year = 2026, Months = [1, 2, 3] });
        foreach (var f in filters)
        {
            var period = PeriodResolver.Resolve(f, 20260901, Today);
            Assert.Equal(2026, DateKeys.FromKey(period.AsOfMonthKey).Year);
            var needed = AnalyticsEngine.BaseWindow.ForPeriod(period, horizon);
            Assert.True(yearly.Contains(needed), $"{f.ToQueryString()} needs {needed}");
            Assert.Equal(yearly, AnalyticsEngine.BaseWindow.ForYear(period.AsOfMonthKey, horizon).Covering(needed));
        }
    }

    [Fact]
    public void A_period_outside_the_yearly_window_loads_exactly_what_it_needs()
    {
        var needed = new AnalyticsEngine.BaseWindow(20240101, 20260901, 20240101, 20270301, 20260801, 20270301, 20260901,
            new DateOnly(2024, 1, 1), new DateOnly(2026, 9, 30));
        Assert.Same(needed, AnalyticsEngine.BaseWindow.ForYear(20260901, 6).Covering(needed));
    }
}

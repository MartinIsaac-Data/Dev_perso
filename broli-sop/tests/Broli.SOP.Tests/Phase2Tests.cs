using System.Net;
using Broli.SOP.Application.Analytics;
using Broli.SOP.Application.Calculations;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Settings;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Tests;

public class MrpCalculatorTests
{
    private static readonly DateOnly Today = new(2026, 9, 23);
    private static readonly DateOnly HorizonEnd = new(2027, 1, 31);

    [Fact]
    public void Net_requirement_covers_forecast_and_safety_stock_net_of_stock_and_supply()
    {
        // Σ forecast 4 000 + safety 1 000 − (stock 1 500 + open 1 000) = 2 500 → rounded up to one 18 000 kg container.
        var r = MrpCalculator.Compute(1500, 1000, [1000, 1000, 1000, 1000], 1000, 18000, 57, new DateOnly(2026, 10, 8), HorizonEnd, Today);
        Assert.Equal(4000, r.TotalForecast);
        Assert.Equal(-1500, r.ProjectedStock);
        Assert.Equal(2500, r.NetRequirement);
        Assert.Equal(18000, r.RecommendedOrder);
        Assert.Equal(new DateOnly(2026, 10, 8), r.NeedDate);
        Assert.Equal(new DateOnly(2026, 8, 12), r.OrderByDate);
        Assert.Equal(42, r.DaysLate);
    }

    [Fact]
    public void No_requirement_when_stock_and_supply_cover_the_horizon()
    {
        var r = MrpCalculator.Compute(5000, 2000, [1000, 1000], 500, null, 30, null, HorizonEnd, Today);
        Assert.Equal(0, r.NetRequirement);
        Assert.Equal(0, r.RecommendedOrder);
        Assert.Null(r.NeedDate);
        Assert.Null(r.DaysLate);
    }

    [Fact]
    public void Safety_driven_requirement_is_needed_by_the_end_of_the_horizon_and_not_late()
    {
        var r = MrpCalculator.Compute(1000, 0, [200, 200], 800, null, 30, null, HorizonEnd, Today);
        Assert.Equal(200, r.NetRequirement);
        Assert.Equal(HorizonEnd, r.NeedDate);
        Assert.Equal(HorizonEnd.AddDays(-30), r.OrderByDate);
        Assert.Null(r.DaysLate);
    }

    [Fact]
    public void Negative_inputs_never_create_negative_requirements()
    {
        var r = MrpCalculator.Compute(-50, -10, [-5, 100], -1, null, null, null, HorizonEnd, Today);
        Assert.Equal(100, r.TotalForecast);
        Assert.Equal(100, r.NetRequirement);
    }
}

public class MaterialFlagTests
{
    private static ProductRef Item => new(1, "300154", "FILM", "FILMS", "Films", "Rahma", MaterialType.Packaging, "KG", 18000, 2600, null,
        "S01", "Anatolia", null, null, false, 20, null, "TR", "Turkey", 30);

    private static ProductPosition Pos(CoverageStatus status, double closing, DateOnly? stockout) =>
        new(Item, 20260901, closing, 0, 0, closing, closing, 1000, closing / 1000, status, 1000, 0, false,
            status is CoverageStatus.Critical or CoverageStatus.Risk, 0, 0, null, stockout, 18000);

    private static readonly DateOnly Alert = new(2026, 11, 20);

    [Fact]
    public void Critical_is_shortage_and_late_supply_is_reported()
    {
        var f = MaterialFlags.Compute(Pos(CoverageStatus.Critical, 500, new DateOnly(2026, 10, 1)), 3000, hasLateSupply: true, Alert);
        Assert.Equal([MaterialFlags.Shortage, MaterialFlags.LateSupply], f);
        Assert.Equal("Critical", MaterialFlags.Risk(f));
    }

    [Fact]
    public void Stockout_before_a_replenishment_can_arrive_is_a_risk_but_later_is_not()
    {
        Assert.Contains(MaterialFlags.StockoutRisk, MaterialFlags.Compute(Pos(CoverageStatus.Watch, 2500, new DateOnly(2026, 11, 10)), 3000, false, Alert));
        Assert.DoesNotContain(MaterialFlags.StockoutRisk, MaterialFlags.Compute(Pos(CoverageStatus.Normal, 3800, new DateOnly(2027, 1, 15)), 3000, false, Alert));
    }

    [Fact]
    public void Excess_and_slow_moving()
    {
        var f = MaterialFlags.Compute(Pos(CoverageStatus.Excess, 40000, null), 100, false, Alert);
        Assert.Equal([MaterialFlags.Excess, MaterialFlags.SlowMoving], f);
        Assert.Equal("Medium", MaterialFlags.Risk(f));
        Assert.Equal("OK", MaterialFlags.Risk([]));
    }

    [Fact]
    public void Alert_window_is_lead_time_but_never_shorter_than_the_risk_band()
    {
        var asOf = new DateOnly(2026, 9, 23);
        var s = new CoverageSettings { RiskBelowMonths = 2 };
        Assert.Equal(asOf.AddDays(90), MaterialFlags.AlertDate(asOf, 90, s));
        Assert.Equal(asOf.AddDays(61), MaterialFlags.AlertDate(asOf, 20, s));
        Assert.Equal(asOf.AddDays(61), MaterialFlags.AlertDate(asOf, null, s));
    }
}

public class LeadTimeAndSupplierTests
{
    private static readonly SupplySettings Settings = new() { PortToWarehouseDays = 7, TransitDaysByCountry = new() { ["TR"] = 33 } };

    [Fact]
    public void Standard_transit_prefers_supplier_then_configuration_then_country()
    {
        Assert.Equal(20, LeadTimes.StandardTransitDays(20, "TR", 30, Settings));
        Assert.Equal(33, LeadTimes.StandardTransitDays(null, "TR", 30, Settings));
        Assert.Equal(45, LeadTimes.StandardTransitDays(null, "CN", 45, Settings));
    }

    [Fact]
    public void Lead_time_adds_production_transit_and_port_clearing_for_imports_only()
    {
        ProductRef P(string country, int transit) => new(1, "X", "X", "C", "C", null, MaterialType.RawMaterial, "KG", null, null, null,
            "S", "S", null, null, false, 15, null, country, country, transit);
        Assert.Equal(15 + 33 + 7, LeadTimes.ProductLeadDays(P("TR", 30), Settings));
        Assert.Equal(15 + 3, LeadTimes.ProductLeadDays(P("CM", 3), Settings));
        Assert.Equal(new DateOnly(2026, 10, 8), LeadTimes.EstimatedDelivery(new DateOnly(2026, 10, 1), null, "Douala", Settings));
        Assert.Equal(new DateOnly(2026, 10, 1), LeadTimes.EstimatedDelivery(new DateOnly(2026, 10, 1), null, null, Settings));
    }

    private static AssessedLine Line(SupplyStatus status, DateOnly? required, DateOnly? arrival, double qty, double? delivered, EtaRiskLevel level = EtaRiskLevel.None, int? delay = null)
    {
        var p = new ProductRef(1, "X", "X", "C", "C", null, MaterialType.RawMaterial, "KG", 25000, null, null, "S1", "Sup", null, null, false);
        var l = new SupplyLineData(1, "PO", 1, "S1", "Sup", "TR", "Turkey", qty, delivered, 1, new DateOnly(2026, 1, 1), required, new DateOnly(2026, 2, 1),
            required, arrival, status, "Douala", null, null, null, 30);
        return new AssessedLine(l, p, new EtaAssessment(level, null, delay), null, 1, arrival is { } a ? a.DayNumber - new DateOnly(2026, 2, 1).DayNumber : null);
    }

    [Fact]
    public void Supplier_score_counts_on_time_partial_and_open_risk()
    {
        var s = new SupplySettings { OnTimeToleranceDays = 2, InFullTolerancePct = 95, SupplierOnTimeAlertPct = 75, OtifTargetPct = 90 };
        var lines = new List<AssessedLine>
        {
            Line(SupplyStatus.Delivered, new(2026, 3, 1), new(2026, 3, 2), 100, 100, delay: 1),   // on time (tolerance)
            Line(SupplyStatus.Delivered, new(2026, 3, 1), new(2026, 3, 10), 100, 80, delay: 9),   // late and partial
            Line(SupplyStatus.Shipped, new(2026, 10, 1), null, 100, null, EtaRiskLevel.Critical),
        };
        var score = SupplierScoring.Score(lines, s);
        Assert.Equal(50, score.OnTimePct);
        Assert.Equal(5, score.AvgDelayDays);
        Assert.Equal(1, score.PartialDeliveries);
        Assert.Equal(1, score.OpenOrders);
        Assert.Equal(1, score.InTransitTc);
        Assert.Equal("Critical", score.Risk);
    }
}

public class Phase2ApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    [Fact]
    public async Task Mrp_recommends_orders_with_a_full_horizon()
    {
        var c = await factory.ClientAsync("supply");
        var d = await c.Get<MrpDashboard>("api/mrp");
        Assert.Equal(4, d.HorizonMonths.Count);
        Assert.True(d.SkusWithRequirement > 0);
        var rows = await c.Get<PagedResult<MrpRow>>("api/mrp/rows?pageSize=200");
        Assert.All(rows.Items, r =>
        {
            Assert.Equal(4, r.Forecast.Count);
            Assert.True(r.NetRequirement > 0);
            Assert.True(r.RecommendedOrder >= r.NetRequirement - 0.01);
            Assert.True(double.IsFinite(r.ProjectedStock));
        });
        var late = await c.Get<PagedResult<MrpRow>>("api/mrp/rows?view=late&pageSize=200");
        Assert.All(late.Items, r => Assert.True(r.DaysLate > 0));
    }

    [Theory]
    [InlineData("raw-materials")]
    [InlineData("films")]
    [InlineData("finished-goods")]
    public async Task Materials_dashboards_are_scoped_and_consistent(string kind)
    {
        var c = await factory.ClientAsync("dg");
        var d = await c.Get<MaterialsDashboard>($"api/materials/{kind}");
        var rows = await c.Get<PagedResult<MaterialRow>>($"api/materials/{kind}/rows?pageSize=500");
        Assert.Equal(d.Skus, rows.Total);
        Assert.Equal(d.Skus, d.Families.Sum(f => f.Skus));
        Assert.All(rows.Items, r => Assert.Equal(kind == "finished-goods", r.MaterialType == "Finished Good"));
        if (kind == "films") Assert.All(rows.Items, r => Assert.Equal("Films", r.Category));
        foreach (var flag in d.FlagCounts)
            Assert.Equal(flag.Value, rows.Items.Count(r => r.Flags.Contains(flag.Label)));
    }

    [Fact]
    public async Task Rahma_films_scenario_is_flagged_as_shortage_with_late_supply()
    {
        var c = await factory.ClientAsync("dg");
        var rows = await c.Get<PagedResult<MaterialRow>>("api/materials/films/rows?brands=Rahma&view=Shortage&pageSize=50");
        Assert.NotEmpty(rows.Items);
        Assert.Contains(rows.Items, r => r.Flags.Contains("Late supply") && r.Risk == "Critical");
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync("api/materials/unknown")).StatusCode);
    }

    [Fact]
    public async Task Transit_and_suppliers_report_standard_vs_actual()
    {
        var c = await factory.ClientAsync("logistics");
        var t = await c.Get<TransitDashboard>("api/transit");
        Assert.NotEmpty(t.Lanes);
        Assert.All(t.Lanes, l => Assert.NotNull(l.StandardDays));
        var rows = await c.Get<PagedResult<TransitRow>>("api/transit/rows?view=water&pageSize=100");
        Assert.All(rows.Items, r =>
        {
            Assert.Equal("Shipped", r.Status);
            if (r.Port is not null && r.Eta is { } eta) Assert.Equal(eta.AddDays(t.PortToWarehouseDays), r.EstimatedDelivery);
        });

        var s = await c.Get<SupplierDashboard>("api/suppliers");
        var suppliers = await c.Get<List<SupplierRow>>("api/suppliers/rows");
        Assert.Equal(s.Suppliers, suppliers.Count);
        Assert.All(suppliers, r => Assert.True(r.OnTimePct is null or >= 0 and <= 100));
    }

    [Fact]
    public async Task Phase2_views_and_exports_follow_permissions()
    {
        var sales = await factory.ClientAsync("sales");
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/mrp")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/transit")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/export/supply?format=csv")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await sales.GetAsync("api/materials/finished-goods")).StatusCode);

        var supply = await factory.ClientAsync("supply");
        foreach (var ds in new[] { "mrp", "raw-materials", "films", "finished-goods", "transit", "suppliers" })
        {
            var r = await supply.GetAsync($"api/export/{ds}?format=xlsx");
            Assert.True(r.IsSuccessStatusCode, ds);
            Assert.Equal("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", r.Content.Headers.ContentType?.MediaType);
        }
    }
}

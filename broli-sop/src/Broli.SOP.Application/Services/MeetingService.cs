using System.Globalization;

namespace Broli.SOP.Application.Services;

/// <summary>The one-page S&amp;OP meeting view: Demand, Supply, Inventory, Logistics, Risks, Opportunities, Decisions.</summary>
public sealed class MeetingService(
    ExecutiveService executive,
    IAnalyticsEngine engine,
    RiskService risks,
    ActionService actions,
    ICurrentUser user,
    IClock clock)
{
    private static readonly CultureInfo En = CultureInfo.GetCultureInfo("en-US");

    public async Task<MeetingView> GetAsync(SopFilter filter, CancellationToken ct)
    {
        var d = await executive.GetAsync(filter, ct);
        var s = await engine.GetSnapshotAsync(filter, ct);
        var today = clock.Today;
        KpiCard K(string code) => d.Kpis.First(k => k.Code == code);
        MeetingKpi FromCard(string code, string? label = null)
        {
            var k = K(code);
            var value = k.Value is not { } v ? "—" : k.Format switch
            {
                "percent" => $"{v:0.0}%",
                "signedPercent" => $"{(v > 0 ? "+" : "")}{v:0.0}%",
                "months" => $"{v:0.0} mo",
                "integer" => v.ToString("N0", En),
                _ => $"{v.ToString(v < 100 ? "N1" : "N0", En)} {k.Unit}",
            };
            return new MeetingKpi(label ?? k.Title, value, k.Subtitle, k.Status, k.DrillUrl);
        }

        // Demand
        var tol = s.Settings.Forecast.OnTrackTolerancePct;
        var demandItems = s.DemandIn(s.Period.MonthKeys).GroupBy(p => p.ProductId)
            .Select(g => (Pos: s.Positions.GetValueOrDefault(g.Key), F: g.Sum(x => x.Forecast), A: g.Sum(x => x.Actual)))
            .Where(x => x.Pos is not null && KpiMath.VariancePct(x.F, x.A) is { } v && Math.Abs(v) > tol)
            .OrderByDescending(x => Math.Abs(x.A - x.F) * (x.Pos!.Product.UnitCost ?? 1))
            .Take(4)
            .Select(x => new MeetingItem(x.Pos!.Product.Description,
                $"Forecast {x.F.ToString("N0", En)} vs actual {x.A.ToString("N0", En)} {x.Pos.Product.Unit} ({KpiMath.VariancePct(x.F, x.A):+0;-0}%)",
                x.A > x.F ? "high" : "medium", $"products/{Uri.EscapeDataString(x.Pos.Product.CArtSap)}"))
            .ToList();

        // Supply
        var pos = s.Positions.Values.ToList();
        var productionTc = s.Period.MonthKeys.Sum(m => pos.Sum(p => p.Tc(s.Production.GetValueOrDefault((p.Product.Id, m))) ?? 0));
        var open = s.FilterLines(filter).Where(l => l.IsOpen).ToList();
        var arriving = open.Where(l => l.Line.Eta is { } e && e <= today.AddDays(30)).Sum(l => l.Tc ?? 0);
        var mrp = MrpService.Build(s, user.Has(Contracts.Security.Permissions.FinanceView));
        var lateOrders = mrp.Where(r => r.DaysLate > 0).OrderByDescending(r => r.DaysLate).ToList();

        // Inventory
        var excess = pos.Where(p => p.Status == CoverageStatus.Excess).ToList();

        // Risks & opportunities
        var detected = RiskDetector.Detect(s, s.FilterLines(filter));
        var register = (await risks.GetAllRegisterAsync(new TableQuery { View = "open" }, ct)).ToList();

        var allActions = await actions.ListAllAsync(new ActionQuery { View = "active" }, ct);
        return new MeetingView(
            s.Period.Info,
            clock.UtcNow,
            new MeetingSection("Demand", "Is demand where we planned it?",
                [FromCard("FORECAST_ACCURACY"), FromCard("FVA", "Actual vs forecast"), FromCard("SERVICE_LEVEL")], demandItems, "demand"),
            new MeetingSection("Supply", "Can supply and production follow?",
                [FromCard("TOTAL_STOCK"),
                 new("Production (period)", $"{productionTc.ToString("N1", En)} TC", "finished goods produced", "neutral", "finished-goods"),
                 new("Imports ≤ 30 days", $"{arriving.ToString("N1", En)} TC", $"{open.Count(l => l.Line.Eta is { } e && e <= today.AddDays(30))} shipments", "neutral", "transit?view=arriving"),
                 new("Orders already late", lateOrders.Count.ToString(En), "MRP order-by date passed", lateOrders.Count > 0 ? "bad" : "good", "mrp?view=late")],
                lateOrders.Take(4).Select(r => new MeetingItem(r.Description,
                    $"Order {r.RecommendedOrder.ToString("N0", En)} {r.Unit} — {r.DaysLate} d late, needed {r.NeedDate:dd/MM}", "critical",
                    $"products/{Uri.EscapeDataString(r.CArtSap)}")).ToList(), "mrp"),
            new MeetingSection("Inventory", "Do we have the right stock?",
                [FromCard("COVERAGE"), FromCard("STOCK_AT_RISK", "Shortage / at risk"),
                 new("Excess", $"{excess.Count} SKUs", $"{excess.Sum(p => p.Tc(p.Excess) ?? 0).ToString("N1", En)} TC above {s.Settings.Coverage.ExcessAboveMonths:0.#} months",
                     excess.Count > 0 ? "watch" : "good", "inventory?view=excess")],
                d.TopRisks.Take(4).Select(r => new MeetingItem(r.Description,
                    $"{r.CoverageMonths:0.0} months of cover" + (r.StockoutDate is { } so ? $", stockout {so:dd/MM}" : "") + (r.NextEta is { } eta ? $", next ETA {eta:dd/MM}" : ", no inbound"),
                    r.CoverageStatus == "Critical" ? "critical" : "high", $"products/{Uri.EscapeDataString(r.CArtSap)}")).ToList(), "inventory?view=at-risk"),
            new MeetingSection("Logistics", "Are imports arriving on time?",
                [FromCard("TC_TRANSIT"), FromCard("TC_PORT"),
                 new("Late shipments", open.Count(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk).ToString(En),
                     $"{open.Count(l => l.Assessment.Level == EtaRiskLevel.Critical)} arrive after the stockout",
                     open.Any(l => l.Assessment.Level == EtaRiskLevel.Critical) ? "bad" : "neutral", "transit?view=late")],
                d.LateSupply.Take(4).Select(l => new MeetingItem($"PO {l.PoNumber} · {l.Product}", l.RiskReason, l.RiskLevel == "Critical" ? "critical" : "high",
                    $"products/{Uri.EscapeDataString(l.CArtSap)}")).ToList(), "transit"),
            new MeetingSection("Risks", "What could hurt service or cash?",
                [new("Critical detected", detected.Count(x => x.Severity == "Critical").ToString(En), "found in the current data", detected.Any(x => x.Severity == "Critical") ? "bad" : "good", "risks"),
                 new("Open in register", register.Count(r => !r.IsOpportunity).ToString(En), $"{register.Count(r => !r.IsOpportunity && r.IsOverdue)} overdue", "neutral", "risks")],
                register.Where(r => !r.IsOpportunity).OrderByDescending(r => r.Score).Take(5)
                    .Select(r => new MeetingItem($"{r.Code} · {r.Description}", $"{r.Category} · impact {r.Impact} · {r.Probability}% · {r.Owner}" + (r.DueDate is { } due ? $" · due {due:dd/MM}" : ""),
                        r.Score >= 12 ? "critical" : r.Score >= 8 ? "high" : "medium", "risks")).ToList(), "risks"),
            new MeetingSection("Opportunities", "Where can we win?",
                [new("Open opportunities", register.Count(r => r.IsOpportunity).ToString(En), "in the register", "neutral", "risks"),
                 new("Demand increases", detected.Count(x => x.Category == "Demand Increase").ToString(En), "forecast well above recent sales", "neutral", "risks")],
                register.Where(r => r.IsOpportunity).OrderByDescending(r => r.Score).Take(3)
                    .Select(r => new MeetingItem($"{r.Code} · {r.Description}", $"{r.Owner}" + (r.Action is null ? "" : $" · {r.Action}"), "good", "risks"))
                    .Concat(detected.Where(x => x.Category == "Demand Increase").Take(2)
                        .Select(x => new MeetingItem(x.Product, x.Title, "good", $"products/{Uri.EscapeDataString(x.CArtSap)}"))).ToList(), "risks"),
            allActions.Where(a => a.IsDecision).OrderBy(a => a.DueDate ?? DateOnly.MaxValue).ToList(),
            allActions.Where(a => a.IsOverdue && !a.IsDecision).OrderBy(a => a.DueDate).Take(10).ToList());
    }
}

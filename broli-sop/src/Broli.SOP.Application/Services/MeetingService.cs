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
    private static readonly CultureInfo Fr = CultureInfo.GetCultureInfo("fr-FR");

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
                "percent" => $"{v:0.0} %",
                "signedPercent" => $"{(v > 0 ? "+" : "")}{v:0.0} %",
                "months" => $"{v:0.0} mois",
                "integer" => v.ToString("N0", Fr),
                _ => $"{v.ToString(v < 100 ? "N1" : "N0", Fr)} {k.Unit}",
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
                $"Prévision {x.F.ToString("N0", Fr)} pour un réel de {x.A.ToString("N0", Fr)} {x.Pos.Product.Unit} ({KpiMath.VariancePct(x.F, x.A):+0;-0} %)",
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
            new MeetingSection("Demande", "La demande est-elle conforme au plan ?",
                [FromCard("FORECAST_ACCURACY"), FromCard("FVA", "Réel / prévision"), FromCard("SERVICE_LEVEL")], demandItems, "demand"),
            new MeetingSection("Approvisionnement", "Les achats et la production peuvent-ils suivre ?",
                [FromCard("TOTAL_STOCK"),
                 new("Production (période)", $"{productionTc.ToString("N1", Fr)} TC", "produits finis fabriqués", "neutral", "finished-goods"),
                 new("Imports ≤ 30 jours", $"{arriving.ToString("N1", Fr)} TC", $"{open.Count(l => l.Line.Eta is { } e && e <= today.AddDays(30))} expéditions", "neutral", "transit?view=arriving"),
                 new("Commandes déjà en retard", lateOrders.Count.ToString(Fr), "date limite de commande MRP dépassée", lateOrders.Count > 0 ? "bad" : "good", "mrp?view=late")],
                lateOrders.Take(4).Select(r => new MeetingItem(r.Description,
                    $"Commander {r.RecommendedOrder.ToString("N0", Fr)} {r.Unit} — {r.DaysLate} j de retard, besoin le {r.NeedDate:dd/MM}", "critical",
                    $"products/{Uri.EscapeDataString(r.CArtSap)}")).ToList(), "mrp"),
            new MeetingSection("Stock", "Avons-nous le bon stock ?",
                [FromCard("COVERAGE"), FromCard("STOCK_AT_RISK", "Pénurie / à risque"),
                 new("Excédent", $"{excess.Count} article{(excess.Count > 1 ? "s" : "")}", $"{excess.Sum(p => p.Tc(p.Excess) ?? 0).ToString("N1", Fr)} TC au-delà de {s.Settings.Coverage.ExcessAboveMonths:0.#} mois",
                     excess.Count > 0 ? "watch" : "good", "inventory?view=excess")],
                d.TopRisks.Take(4).Select(r => new MeetingItem(r.Description,
                    $"{r.CoverageMonths:0.0} mois de couverture" + (r.StockoutDate is { } so ? $", rupture le {so:dd/MM}" : "") + (r.NextEta is { } eta ? $", prochaine ETA le {eta:dd/MM}" : ", aucun arrivage"),
                    r.CoverageStatus == Labels.Of(CoverageStatus.Critical) ? "critical" : "high", $"products/{Uri.EscapeDataString(r.CArtSap)}")).ToList(), "inventory?view=at-risk"),
            new MeetingSection("Logistique", "Les imports arrivent-ils à temps ?",
                [FromCard("TC_TRANSIT"), FromCard("TC_PORT"),
                 new("Expéditions en retard", open.Count(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk).ToString(Fr),
                     $"{open.Count(l => l.Assessment.Level == EtaRiskLevel.Critical)} arrivent après la rupture",
                     open.Any(l => l.Assessment.Level == EtaRiskLevel.Critical) ? "bad" : "neutral", "transit?view=late")],
                d.LateSupply.Take(4).Select(l => new MeetingItem($"Commande {l.PoNumber} · {l.Product}", l.RiskReason, l.RiskLevel == Labels.Of(EtaRiskLevel.Critical) ? "critical" : "high",
                    $"products/{Uri.EscapeDataString(l.CArtSap)}")).ToList(), "transit"),
            new MeetingSection("Risques", "Qu'est-ce qui menace le service ou la trésorerie ?",
                [new("Critiques détectés", detected.Count(x => x.Severity == Labels.Of(ImpactLevel.Critical)).ToString(Fr), "dans les données actuelles", detected.Any(x => x.Severity == Labels.Of(ImpactLevel.Critical)) ? "bad" : "good", "risks"),
                 new("Ouverts au registre", register.Count(r => !r.IsOpportunity).ToString(Fr), $"{register.Count(r => !r.IsOpportunity && r.IsOverdue)} en retard", "neutral", "risks")],
                register.Where(r => !r.IsOpportunity).OrderByDescending(r => r.Score).Take(5)
                    .Select(r => new MeetingItem($"{r.Code} · {r.Description}", $"{r.Category} · impact {r.Impact.ToLowerInvariant()} · {r.Probability} % · {r.Owner}" + (r.DueDate is { } due ? $" · échéance {due:dd/MM}" : ""),
                        r.Score >= 12 ? "critical" : r.Score >= 8 ? "high" : "medium", "risks")).ToList(), "risks"),
            new MeetingSection("Opportunités", "Où pouvons-nous gagner ?",
                [new("Opportunités ouvertes", register.Count(r => r.IsOpportunity).ToString(Fr), "au registre", "neutral", "risks"),
                 new("Hausses de demande", detected.Count(x => x.Category == Labels.Of(RiskCategory.DemandIncrease)).ToString(Fr), "prévision nettement au-dessus des ventes récentes", "neutral", "risks")],
                register.Where(r => r.IsOpportunity).OrderByDescending(r => r.Score).Take(3)
                    .Select(r => new MeetingItem($"{r.Code} · {r.Description}", $"{r.Owner}" + (r.Action is null ? "" : $" · {r.Action}"), "good", "risks"))
                    .Concat(detected.Where(x => x.Category == Labels.Of(RiskCategory.DemandIncrease)).Take(2)
                        .Select(x => new MeetingItem(x.Product, x.Title, "good", $"products/{Uri.EscapeDataString(x.CArtSap)}"))).ToList(), "risks"),
            allActions.Where(a => a.IsDecision).OrderBy(a => a.DueDate ?? DateOnly.MaxValue).ToList(),
            allActions.Where(a => a.IsOverdue && !a.IsDecision).OrderBy(a => a.DueDate).Take(10).ToList());
    }
}

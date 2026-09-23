using System.Globalization;

namespace Broli.SOP.Application.Calculations;

/// <summary>
/// Turns a product position and its inbound supply into concrete, ranked recommendations:
/// what a planner should do next, and why.
/// </summary>
public static class ActionAdvisor
{
    private static readonly CultureInfo Fr = CultureInfo.GetCultureInfo("fr-FR");

    public static IReadOnlyList<RecommendedAction> Advise(ProductPosition pos, IReadOnlyList<AssessedLine> openLines, SopSettings settings, DateOnly today)
    {
        var actions = new List<RecommendedAction>();
        var p = pos.Product;
        var unit = p.Unit;
        var cs = settings.Coverage;

        if (pos.Status == CoverageStatus.NoDemand)
        {
            if (pos.Closing > 0)
                actions.Add(new("medium", "Dormant stock — no demand",
                    $"{Q(pos.Closing)} {unit} in stock with no consumption or forecast. Review with Sales (slow moving) or plan a clearance.", null));
            return actions.Count > 0 ? actions : [new("info", "No action required", "No stock and no demand for this item.", null)];
        }

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.Critical))
            actions.Add(new("critical", $"Expedite PO {l.Line.PoNumber} ({l.Line.SupplierName})",
                $"{l.Assessment.Reason}. Ask the supplier for an earlier shipment, a partial delivery or an alternative source.", l.Line.PoNumber));

        var target = cs.WatchBelowMonths * pos.AvgConsumption;
        var net = Math.Max(0, target - (pos.Closing + pos.OpenQty));
        var stockoutSoon = pos.StockoutDate is { } so && so <= today.AddMonths((int)Math.Ceiling(cs.RiskBelowMonths));
        if ((pos.AtRisk || stockoutSoon) && net > 0)
        {
            var qty = KpiMath.RoundUpToMultiple(net, pos.UnitsPerTc is { } u && p.MaterialType != MaterialType.FinishedGood ? u : null);
            var tc = pos.Tc(qty) is { } t ? $" (~{t:0.#} TC)" : "";
            var when = pos.StockoutDate is { } d ? $", projected stockout {d.ToString("dd/MM/yyyy", Fr)}" : "";
            var severity = pos.Status == CoverageStatus.Critical ? "critical" : "high";
            if (p.MaterialType == MaterialType.FinishedGood)
                actions.Add(new(severity, $"Increase production by {Q(qty)} {unit}",
                    $"Coverage {C(pos.CoverageMonths)}{when}. Open supply does not reach the {cs.WatchBelowMonths:0.#}-month target. Check raw-material availability.", null));
            else
                actions.Add(new(severity, $"Place a purchase order: {Q(qty)} {unit}{tc}",
                    $"Coverage {C(pos.CoverageMonths)}{when}. Stock + open orders ({Q(pos.Closing + pos.OpenQty)} {unit}) are below the {cs.WatchBelowMonths:0.#}-month target"
                    + (p.MainSupplierName is { } s ? $". Main supplier: {s}." : "."), null));
        }

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.SupplyRisk))
            actions.Add(new("high", $"Follow up PO {l.Line.PoNumber} with {l.Line.SupplierName}", $"{l.Assessment.Reason}. Confirm a firm ETA.", l.Line.PoNumber));

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.Watch))
            actions.Add(new("medium", $"Monitor PO {l.Line.PoNumber}", l.Assessment.Reason ?? "ETA close to requirement.", l.Line.PoNumber));

        if (pos.Status == CoverageStatus.Excess)
            actions.Add(new("medium", $"Reduce excess stock ({Q(pos.Excess)} {unit})",
                $"Coverage {C(pos.CoverageMonths)} exceeds {cs.ExcessAboveMonths:0.#} months."
                + (pos.OpenQty > 0 ? $" Postpone or cancel open orders ({Q(pos.OpenQty)} {unit})." : " Consider a sales push."), null));

        if (pos.BelowSafety && !pos.AtRisk && actions.Count == 0)
            actions.Add(new("medium", "Stock below safety stock",
                $"Available {Q(pos.Available)} {unit} vs safety stock {Q(pos.SafetyStock)} {unit}. Monitor the next receipts.", null));

        if (actions.Count == 0)
            actions.Add(new("info", "No action required", $"Coverage {C(pos.CoverageMonths)} is within target.", null));

        return actions;
    }

    internal static string Q(double v) => v.ToString("#,0", Fr);
    internal static string C(double? months) => months is { } m ? $"{m:0.0} months" : "n/a";
}

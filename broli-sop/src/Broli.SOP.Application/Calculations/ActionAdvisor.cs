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
                actions.Add(new("medium", "Stock dormant — aucune demande",
                    $"{Q(pos.Closing)} {unit} en stock sans consommation ni prévision. À revoir avec les ventes (rotation lente) ou prévoir un déstockage.", null));
            return actions.Count > 0 ? actions : [new("info", "Aucune action nécessaire", "Ni stock ni demande pour cet article.", null)];
        }

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.Critical))
            actions.Add(new("critical", $"Accélérer la commande {l.Line.PoNumber} ({l.Line.SupplierName})",
                $"{l.Assessment.Reason}. Demander au fournisseur une expédition plus tôt, une livraison partielle ou une source alternative.", l.Line.PoNumber));

        var target = cs.WatchBelowMonths * pos.AvgConsumption;
        var net = Math.Max(0, target - (pos.Closing + pos.OpenQty));
        var stockoutSoon = pos.StockoutDate is { } so && so <= today.AddMonths((int)Math.Ceiling(cs.RiskBelowMonths));
        if ((pos.AtRisk || stockoutSoon) && net > 0)
        {
            var qty = KpiMath.RoundUpToMultiple(net, pos.UnitsPerTc is { } u && p.MaterialType != MaterialType.FinishedGood ? u : null);
            var tc = pos.Tc(qty) is { } t ? $" (~{t:0.#} TC)" : "";
            var when = pos.StockoutDate is { } d ? $", rupture prévue le {d.ToString("dd/MM/yyyy", Fr)}" : "";
            var severity = pos.Status == CoverageStatus.Critical ? "critical" : "high";
            if (p.MaterialType == MaterialType.FinishedGood)
                actions.Add(new(severity, $"Augmenter la production de {Q(qty)} {unit}",
                    $"Couverture {C(pos.CoverageMonths)}{when}. Les approvisionnements en cours n'atteignent pas l'objectif de {cs.WatchBelowMonths:0.#} mois. Vérifier la disponibilité des matières premières.", null));
            else
                actions.Add(new(severity, $"Passer une commande : {Q(qty)} {unit}{tc}",
                    $"Couverture {C(pos.CoverageMonths)}{when}. Stock + commandes en cours ({Q(pos.Closing + pos.OpenQty)} {unit}) sous l'objectif de {cs.WatchBelowMonths:0.#} mois"
                    + (p.MainSupplierName is { } s ? $". Fournisseur principal : {s}." : "."), null));
        }

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.SupplyRisk))
            actions.Add(new("high", $"Relancer {l.Line.SupplierName} sur la commande {l.Line.PoNumber}", $"{l.Assessment.Reason}. Obtenir une ETA ferme.", l.Line.PoNumber));

        foreach (var l in openLines.Where(l => l.Assessment.Level == EtaRiskLevel.Watch))
            actions.Add(new("medium", $"Surveiller la commande {l.Line.PoNumber}", l.Assessment.Reason ?? "ETA proche du besoin.", l.Line.PoNumber));

        if (pos.Status == CoverageStatus.Excess)
            actions.Add(new("medium", $"Réduire le stock excédentaire ({Q(pos.Excess)} {unit})",
                $"La couverture de {C(pos.CoverageMonths)} dépasse {cs.ExcessAboveMonths:0.#} mois."
                + (pos.OpenQty > 0 ? $" Reporter ou annuler les commandes en cours ({Q(pos.OpenQty)} {unit})." : " Envisager une action commerciale."), null));

        if (pos.BelowSafety && !pos.AtRisk && actions.Count == 0)
            actions.Add(new("medium", "Stock sous le stock de sécurité",
                $"Disponible {Q(pos.Available)} {unit} pour un stock de sécurité de {Q(pos.SafetyStock)} {unit}. Surveiller les prochaines réceptions.", null));

        if (actions.Count == 0)
            actions.Add(new("info", "Aucune action nécessaire", $"La couverture de {C(pos.CoverageMonths)} est dans l'objectif.", null));

        return actions;
    }

    internal static string Q(double v) => v.ToString("#,0", Fr);
    internal static string C(double? months) => months is { } m ? $"{m.ToString("0.0", Fr)} mois" : "n.d.";
}

using System.Globalization;

namespace Broli.SOP.Application.Services;

/// <summary>
/// Scans a snapshot and lists the risks the data already shows — stockouts, late supply,
/// port/customs delays, excess and dormant stock, forecast bias and demand surges —
/// each with a suggested action. Nothing is stored: the list is always current.
/// </summary>
public static class RiskDetector
{
    private static readonly CultureInfo Fr = CultureInfo.GetCultureInfo("fr-FR");

    public static IReadOnlyList<DetectedRisk> Detect(AnalyticsSnapshot s, IEnumerable<AssessedLine> lines)
    {
        var set = s.Settings;
        var result = new List<DetectedRisk>();
        var openByProduct = lines.Where(l => l.IsOpen).GroupBy(l => l.Product.Id).ToDictionary(g => g.Key, g => g.ToList());

        foreach (var pos in s.Positions.Values)
        {
            var p = pos.Product;
            var open = openByProduct.GetValueOrDefault(p.Id) ?? [];
            string Suggest() => ActionAdvisor.Advise(pos, open, set, s.Today)[0].Title;

            if (pos.AtRisk)
            {
                var severity = pos.Status == CoverageStatus.Critical ? Labels.Of(ImpactLevel.Critical) : Labels.Of(ImpactLevel.High);
                result.Add(new DetectedRisk(Labels.Of(RiskCategory.Stockout), severity, p.CArtSap, p.Description,
                    $"Couverture {Months(pos.CoverageMonths)} — {Labels.Of(pos.Status)}",
                    $"Stock {Q(pos.Closing)} {p.Unit}, consommation {Q(pos.AvgConsumption)} {p.Unit}/mois"
                    + (pos.StockoutDate is { } so ? $", rupture prévue le {so.ToString("dd/MM/yyyy", Fr)}" : "")
                    + (pos.OpenQty > 0 ? $", approvisionnement en cours {Q(pos.OpenQty)} {p.Unit}" : ", aucun approvisionnement en cours"),
                    Suggest(), null, pos.StockoutDate));
            }
            else if (pos.Status == CoverageStatus.Excess)
            {
                result.Add(new DetectedRisk(Labels.Of(RiskCategory.Overstock), Labels.Of(ImpactLevel.Medium), p.CArtSap, p.Description,
                    $"Couverture {Months(pos.CoverageMonths)} — au-delà de {set.Coverage.ExcessAboveMonths:0.#} mois",
                    $"Excédent {Q(pos.Excess)} {p.Unit}" + (pos.OpenQty > 0 ? $", encore {Q(pos.OpenQty)} {p.Unit} en commande" : ""),
                    Suggest(), null, null));
            }
            else if (pos.Status == CoverageStatus.NoDemand && pos.Closing > 0)
            {
                result.Add(new DetectedRisk(Labels.Of(RiskCategory.ExcessStock), Labels.Of(ImpactLevel.Low), p.CArtSap, p.Description,
                    "Stock dormant — aucune demande", $"{Q(pos.Closing)} {p.Unit} sans consommation ni prévision", Suggest(), null, null));
            }

            // Forecast bias over the last three months up to the as-of month.
            var recent = Enumerable.Range(0, 3).Select(i => DateKeys.AddMonths(s.Period.AsOfMonthKey, -i)).ToHashSet();
            var dem = s.DemandByProduct[p.Id].Where(d => recent.Contains(d.MonthKey)).ToList();
            var fSum = dem.Sum(d => d.Forecast);
            var aSum = dem.Sum(d => d.Actual);
            if (KpiMath.BiasPct(fSum, aSum) is { } bias && Math.Abs(bias) > 2 * set.Forecast.OnTrackTolerancePct && aSum > 0)
            {
                result.Add(new DetectedRisk(Labels.Of(RiskCategory.ForecastRisk), Math.Abs(bias) > 4 * set.Forecast.OnTrackTolerancePct ? Labels.Of(ImpactLevel.High) : Labels.Of(ImpactLevel.Medium),
                    p.CArtSap, p.Description,
                    $"Biais de prévision de {bias:+0;-0} % sur 3 mois",
                    bias > 0 ? $"Prévision {Q(fSum)} pour un réel de {Q(aSum)} {p.Unit} : la surprévision crée du stock excédentaire."
                             : $"Prévision {Q(fSum)} pour un réel de {Q(aSum)} {p.Unit} : la sous-prévision crée des ruptures.",
                    "Revoir la prévision avec les ventes à la prochaine réunion S&OP", null, null));
            }

            // Demand increase: upcoming forecast well above recent history.
            var hist = Enumerable.Range(0, 3).Select(i => s.Consumption.GetValueOrDefault((p.Id, DateKeys.AddMonths(s.Period.AsOfMonthKey, -i)))).Average();
            var fn = s.DemandFn(p.Id);
            var next = Enumerable.Range(1, 3).Select(i => fn(DateKeys.AddMonths(s.Period.AsOfMonthKey, i))).Average();
            if (hist > 0 && next > hist * (1 + set.Forecast.DemandIncreaseThresholdPct / 100))
            {
                result.Add(new DetectedRisk(Labels.Of(RiskCategory.DemandIncrease), Labels.Of(ImpactLevel.Medium), p.CArtSap, p.Description,
                    $"Prévision +{(next / hist - 1) * 100:0} % par rapport aux 3 derniers mois",
                    $"Moyenne des 3 prochains mois : {Q(next)} contre {Q(hist)} {p.Unit}/mois. Vérifier la capacité et les approvisionnements.",
                    "Confirmer les approvisionnements et la capacité de production", null, null));
            }
        }

        foreach (var l in lines.Where(l => l.IsOpen && l.Assessment.Level >= EtaRiskLevel.SupplyRisk))
        {
            var atPort = l.Line.Status.IsAtPort();
            var category = Labels.Of(!atPort ? RiskCategory.SupplyDelay : l.Line.Status == SupplyStatus.Customs ? RiskCategory.Customs : RiskCategory.PortDelay);
            result.Add(new DetectedRisk(category, l.Assessment.Level == EtaRiskLevel.Critical ? Labels.Of(ImpactLevel.Critical) : Labels.Of(ImpactLevel.High),
                l.Product.CArtSap, l.Product.Description,
                $"Commande {l.Line.PoNumber} — {l.Line.SupplierName}",
                l.Assessment.Reason ?? "",
                l.Assessment.Level == EtaRiskLevel.Critical ? "Accélérer l'expédition / trouver une source alternative" : atPort ? "Relancer le dédouanement avec le transitaire" : "Obtenir une ETA ferme du fournisseur",
                l.Line.PoNumber, l.StockoutDate ?? l.Line.RequiredDate));
        }

        return result
            .OrderBy(r => SeverityRank(r.Severity))
            .ThenBy(r => r.DueBy ?? DateOnly.MaxValue)
            .ToList();
    }

    public static int SeverityRank(string severity) =>
        Labels.TryParse<ImpactLevel>(severity, out var level) ? ImpactLevel.Critical - level : 3;

    private static string Q(double v) => v.ToString("#,0", Fr);
    private static string Months(double? m) => m is { } v ? $"{v.ToString("0.0", Fr)} mois" : "n.d.";
}

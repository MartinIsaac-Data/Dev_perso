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
                var severity = pos.Status == CoverageStatus.Critical ? "Critical" : "High";
                result.Add(new DetectedRisk("Stockout", severity, p.CArtSap, p.Description,
                    $"Coverage {Months(pos.CoverageMonths)} — {Labels.Of(pos.Status)}",
                    $"Stock {Q(pos.Closing)} {p.Unit}, consumption {Q(pos.AvgConsumption)} {p.Unit}/month"
                    + (pos.StockoutDate is { } so ? $", projected stockout {so.ToString("dd/MM/yyyy", Fr)}" : "")
                    + (pos.OpenQty > 0 ? $", open supply {Q(pos.OpenQty)} {p.Unit}" : ", no open supply"),
                    Suggest(), null, pos.StockoutDate));
            }
            else if (pos.Status == CoverageStatus.Excess)
            {
                result.Add(new DetectedRisk("Overstock", "Medium", p.CArtSap, p.Description,
                    $"Coverage {Months(pos.CoverageMonths)} — above {set.Coverage.ExcessAboveMonths:0.#} months",
                    $"Excess {Q(pos.Excess)} {p.Unit}" + (pos.OpenQty > 0 ? $", still {Q(pos.OpenQty)} {p.Unit} on order" : ""),
                    Suggest(), null, null));
            }
            else if (pos.Status == CoverageStatus.NoDemand && pos.Closing > 0)
            {
                result.Add(new DetectedRisk("Excess Stock", "Low", p.CArtSap, p.Description,
                    "Dormant stock — no demand", $"{Q(pos.Closing)} {p.Unit} with no consumption or forecast", Suggest(), null, null));
            }

            // Forecast bias over the last three months up to the as-of month.
            var recent = Enumerable.Range(0, 3).Select(i => DateKeys.AddMonths(s.Period.AsOfMonthKey, -i)).ToHashSet();
            var dem = s.DemandByProduct[p.Id].Where(d => recent.Contains(d.MonthKey)).ToList();
            var fSum = dem.Sum(d => d.Forecast);
            var aSum = dem.Sum(d => d.Actual);
            if (KpiMath.BiasPct(fSum, aSum) is { } bias && Math.Abs(bias) > 2 * set.Forecast.OnTrackTolerancePct && aSum > 0)
            {
                result.Add(new DetectedRisk("Forecast Risk", Math.Abs(bias) > 4 * set.Forecast.OnTrackTolerancePct ? "High" : "Medium",
                    p.CArtSap, p.Description,
                    $"Forecast bias {bias:+0;-0}% over 3 months",
                    bias > 0 ? $"Forecast {Q(fSum)} vs actual {Q(aSum)} {p.Unit}: over-forecast drives excess stock."
                             : $"Forecast {Q(fSum)} vs actual {Q(aSum)} {p.Unit}: under-forecast drives shortages.",
                    "Review the forecast with Sales at the next S&OP", null, null));
            }

            // Demand increase: upcoming forecast well above recent history.
            var hist = Enumerable.Range(0, 3).Select(i => s.Consumption.GetValueOrDefault((p.Id, DateKeys.AddMonths(s.Period.AsOfMonthKey, -i)))).Average();
            var fn = s.DemandFn(p.Id);
            var next = Enumerable.Range(1, 3).Select(i => fn(DateKeys.AddMonths(s.Period.AsOfMonthKey, i))).Average();
            if (hist > 0 && next > hist * (1 + set.Forecast.DemandIncreaseThresholdPct / 100))
            {
                result.Add(new DetectedRisk("Demand Increase", "Medium", p.CArtSap, p.Description,
                    $"Forecast +{(next / hist - 1) * 100:0}% vs last 3 months",
                    $"Next 3 months average {Q(next)} vs {Q(hist)} {p.Unit}/month. Check capacity and supply.",
                    "Confirm supply and production capacity", null, null));
            }
        }

        foreach (var l in lines.Where(l => l.IsOpen && l.Assessment.Level >= EtaRiskLevel.SupplyRisk))
        {
            var atPort = l.Line.Status.IsAtPort();
            var category = !atPort ? "Supply Delay" : l.Line.Status == SupplyStatus.Customs ? "Customs" : "Port Delay";
            result.Add(new DetectedRisk(category, l.Assessment.Level == EtaRiskLevel.Critical ? "Critical" : "High",
                l.Product.CArtSap, l.Product.Description,
                $"PO {l.Line.PoNumber} — {l.Line.SupplierName}",
                l.Assessment.Reason ?? "",
                l.Assessment.Level == EtaRiskLevel.Critical ? "Expedite shipment / find alternative supply" : atPort ? "Escalate clearing with the transit agent" : "Obtain a firm ETA from the supplier",
                l.Line.PoNumber, l.StockoutDate ?? l.Line.RequiredDate));
        }

        return result
            .OrderBy(r => SeverityRank(r.Severity))
            .ThenBy(r => r.DueBy ?? DateOnly.MaxValue)
            .ToList();
    }

    public static int SeverityRank(string severity) => severity switch
    {
        "Critical" => 0,
        "High" => 1,
        "Medium" => 2,
        _ => 3,
    };

    private static string Q(double v) => v.ToString("#,0", Fr);
    private static string Months(double? m) => m is { } v ? $"{v:0.0} months" : "n/a";
}

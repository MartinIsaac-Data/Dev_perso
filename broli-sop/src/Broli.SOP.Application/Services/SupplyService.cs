using System.Globalization;

namespace Broli.SOP.Application.Services;

public sealed class SupplyService(
    IAnalyticsEngine engine,
    ISupplyRepository repository,
    IAuditLogger audit,
    IDataVersion version)
{
    public async Task<SupplyDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var lines = s.FilterLines(filter).ToList();
        var open = lines.Where(l => l.IsOpen).ToList();
        var delivered = lines.DeliveredIn(s.Period.MonthKeys).ToList();

        var summary = new SupplySummary(
            open.Count,
            Mapping.R(open.Sum(l => l.Tc ?? 0)),
            Mapping.R(open.Where(l => l.Line.Status.IsInTransit()).Sum(l => l.Tc ?? 0)),
            Mapping.R(open.Where(l => l.Line.Status.IsAtPort()).Sum(l => l.Tc ?? 0)),
            open.Count(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk),
            open.Count(l => l.Assessment.Level == EtaRiskLevel.Critical),
            Mapping.R(delivered.OtifPct(s.Settings.Supply)),
            Mapping.R(delivered.Where(l => l.Assessment.DelayDays.HasValue).Select(l => (double)l.Assessment.DelayDays!.Value).DefaultIfEmpty().Average()),
            Mapping.R(lines.Where(l => l.TransitDays.HasValue).Select(l => (double)l.TransitDays!.Value).DefaultIfEmpty().Average()));

        var byStatus = open.GroupBy(l => l.Line.Status).OrderBy(g => g.Key)
            .Select(g => new ChartPoint(Labels.Of(g.Key), g.Count(), g.Key.ToString())).ToList();

        // Arrivals over the next 12 weeks, by ISO week of ETA; anything overdue is grouped first.
        var weekStart = s.Today.AddDays(-(((int)s.Today.DayOfWeek + 6) % 7));
        var arrivals = new List<ChartPoint>
        {
            new("Overdue", Mapping.R(open.Where(l => l.Line.Eta is { } e && e < s.Today).Sum(l => l.Tc ?? 0)), "overdue"),
        };
        for (var w = 0; w < 12; w++)
        {
            var from = weekStart.AddDays(7 * w);
            var to = from.AddDays(7);
            var tc = open.Where(l => l.Line.Eta is { } e && e >= from && e < to && e >= s.Today).Sum(l => l.Tc ?? 0);
            arrivals.Add(new($"W{ISOWeek.GetWeekOfYear(from.ToDateTime(TimeOnly.MinValue)):00}", Mapping.R(tc), from.ToString("yyyy-MM-dd")));
        }

        var levels = new[] { EtaRiskLevel.Critical, EtaRiskLevel.SupplyRisk, EtaRiskLevel.Watch, EtaRiskLevel.None }
            .Select(l => new ChartPoint(Labels.Of(l), open.Count(x => x.Assessment.Level == l), l.ToString())).ToList();

        return new SupplyDashboard(s.Period.Info, summary, byStatus, arrivals, levels);
    }

    public async Task<PagedResult<SupplyRow>> GetRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, sort, desc);
    }

    public async Task<IReadOnlyList<SupplyRow>> GetAllRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, sort, desc).ToList();
    }

    private async Task<(IEnumerable<SupplyRow>, string, bool)> RowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var lines = s.FilterLines(filter);
        var view = q.View?.ToLowerInvariant();
        lines = view switch
        {
            "transit" => lines.Where(l => l.IsOpen && l.Line.Status.IsInTransit()),
            "port" => lines.Where(l => l.IsOpen && l.Line.Status.IsAtPort()),
            "late" => lines.Where(l => l.IsOpen && l.Assessment.Level >= EtaRiskLevel.SupplyRisk),
            "critical" => lines.Where(l => l.IsOpen && l.Assessment.Level == EtaRiskLevel.Critical),
            "watch" => lines.Where(l => l.IsOpen && l.Assessment.Level == EtaRiskLevel.Watch),
            "delivered" => lines.DeliveredIn(s.Period.MonthKeys),
            "all" => lines,
            _ => lines.Where(l => l.IsOpen),
        };
        var rows = lines.Select(l => l.ToRow()).ToList();
        return view is "late" or "critical" or "open" or null or "" ? (rows, "Risk", true) : (rows, "Eta", false);
    }

    private static string Search(SupplyRow r) => $"{r.PoNumber} {r.CArtSap} {r.Product} {r.Supplier} {r.SupplierCode} {r.Country} {r.Status} {r.Booking} {r.BillOfLading}";

    private static readonly Dictionary<string, Func<SupplyRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["PoNumber"] = r => r.PoNumber,
        ["CArtSap"] = r => r.CArtSap,
        ["Product"] = r => r.Product,
        ["Supplier"] = r => r.Supplier,
        ["Country"] = r => r.Country,
        ["Quantity"] = r => r.Quantity,
        ["Tc"] = r => r.Tc,
        ["OrderDate"] = r => r.OrderDate,
        ["RequiredDate"] = r => r.RequiredDate,
        ["Etd"] = r => r.Etd,
        ["Eta"] = r => r.Eta,
        ["Status"] = r => r.Status,
        ["DelayDays"] = r => r.DelayDays,
        ["TransitDays"] = r => r.TransitDays,
        ["StockoutDate"] = r => r.StockoutDate,
        ["Risk"] = r => r.RiskLevel switch { "Critical" => 3, "Supply Risk" => 2, "Watch" => 1, _ => 0 },
    };

    /// <summary>Updates ETA / status of a line. Every changed field is written to the audit log.</summary>
    public async Task<bool> UpdateAsync(long id, SupplyUpdateRequest request, CancellationToken ct)
    {
        var line = await repository.FindAsync(id, ct);
        if (line is null) return false;

        var changes = new List<(string Field, string? Old, string? New)>();
        void Track<T>(string field, T oldValue, T newValue, Action apply)
        {
            if (EqualityComparer<T>.Default.Equals(oldValue, newValue)) return;
            changes.Add((field, Fmt(oldValue), Fmt(newValue)));
            apply();
        }

        if (request.Etd is { } etd) Track("ETD", line.Etd, etd, () => line.Etd = etd);
        if (request.Eta is { } eta) Track("ETA", line.Eta, eta, () => line.Eta = eta);
        if (request.ActualArrival is { } arr) Track("Actual arrival", line.ActualArrival, arr, () => line.ActualArrival = arr);
        if (request.CustomsStatus is { } cs) Track("Customs status", line.CustomsStatus, cs, () => line.CustomsStatus = cs);
        if (request.Status is { } st)
        {
            if (!Labels.TryParse<SupplyStatus>(st, out var status)) throw new ArgumentException($"Unknown status '{st}'.");
            Track("Status", line.Status, status, () => line.Status = status);
        }
        if (line.Etd is { } d1 && line.Eta is { } d2 && d2 < d1) throw new ArgumentException("ETA cannot be before ETD.");
        if (line.Status == SupplyStatus.Delivered && line.ActualArrival is null) throw new ArgumentException("A delivered line needs an actual arrival date.");

        if (changes.Count == 0) return true;
        await repository.SaveChangesAsync(ct);
        foreach (var c in changes)
            await audit.LogAsync($"Updated {c.Field}", "Supply", $"PO {line.PoNumber}", c.Old, c.New, ct);
        version.Bump();
        return true;
    }

    private static string? Fmt<T>(T value) => value switch
    {
        null => null,
        DateOnly d => d.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture),
        SupplyStatus s => Labels.Of(s),
        _ => value.ToString(),
    };
}

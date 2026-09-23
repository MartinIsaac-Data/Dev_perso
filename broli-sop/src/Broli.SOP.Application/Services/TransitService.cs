namespace Broli.SOP.Application.Services;

public sealed class TransitService(IAnalyticsEngine engine)
{
    public async Task<TransitDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var set = s.Settings.Supply;
        var lines = s.FilterLines(filter).ToList();
        var open = lines.Where(l => l.IsOpen).ToList();
        var rows = lines.Select(l => Row(l, set)).ToList();
        var shipped = rows.Where(r => r.TransitDays.HasValue && (r.ActualArrival.HasValue || r.Status is "Shipped" or "At Port" or "Customs")).ToList();

        var lanes = lines.Where(l => l.TransitDays.HasValue && l.Line.ActualArrival.HasValue)
            .GroupBy(l => (l.Line.CountryCode, l.Line.CountryName, l.Line.DefaultTransitDays))
            .Select(g =>
            {
                var std = LeadTimes.StandardTransitDays(null, g.Key.CountryCode, g.Key.DefaultTransitDays, set);
                var avg = g.Average(l => (double)l.TransitDays!.Value);
                return new TransitLane(g.Key.CountryName ?? g.Key.CountryCode ?? "?", g.Count(), Mapping.R(avg), std, std is { } sd ? Mapping.R(avg - sd) : null);
            })
            .OrderByDescending(l => l.Shipments).ToList();

        var horizon = s.Today.AddDays(14);
        return new TransitDashboard(
            s.Period.Info,
            open.Count(l => l.Line.Status == SupplyStatus.Shipped),
            open.Count(l => l.Line.Status == SupplyStatus.AtPort),
            open.Count(l => l.Line.Status == SupplyStatus.Customs),
            Mapping.R(open.Where(l => l.Line.Eta is { } e && e <= horizon).Sum(l => l.Tc ?? 0)),
            Mapping.R(shipped.Select(r => (double)r.TransitDays!.Value).DefaultIfEmpty().Average()),
            Mapping.R(shipped.Where(r => r.TransitGapDays.HasValue).Select(r => (double)r.TransitGapDays!.Value).DefaultIfEmpty().Average()),
            open.Count(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk),
            lanes,
            open.GroupBy(l => l.Line.Status).OrderBy(g => g.Key)
                .Select(g => new ChartPoint(Labels.Of(g.Key), Mapping.R(g.Sum(l => l.Tc ?? 0)), g.Key.ToString())).ToList(),
            set.PortToWarehouseDays);
    }

    public async Task<PagedResult<TransitRow>> GetRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(filter, q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, "Eta", false);
    }

    public async Task<IReadOnlyList<TransitRow>> GetAllRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(filter, q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, "Eta", false).ToList();
    }

    private async Task<IEnumerable<TransitRow>> RowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var set = s.Settings.Supply;
        var lines = s.FilterLines(filter);
        var horizon = s.Today.AddDays(14);
        lines = q.View?.ToLowerInvariant() switch
        {
            "water" => lines.Where(l => l.IsOpen && l.Line.Status == SupplyStatus.Shipped),
            "port" => lines.Where(l => l.IsOpen && l.Line.Status == SupplyStatus.AtPort),
            "customs" => lines.Where(l => l.IsOpen && l.Line.Status == SupplyStatus.Customs),
            "arriving" => lines.Where(l => l.IsOpen && l.Line.Eta is { } e && e <= horizon),
            "late" => lines.Where(l => l.IsOpen && l.Assessment.Level >= EtaRiskLevel.SupplyRisk),
            "delivered" => lines.DeliveredIn(s.Period.MonthKeys),
            "all" => lines,
            _ => lines.Where(l => l.IsOpen && (l.Line.Status.IsInTransit() || l.Line.Etd is { } etd && etd <= s.Today)),
        };
        return lines.Select(l => Row(l, set)).ToList();
    }

    internal static TransitRow Row(AssessedLine a, SupplySettings set)
    {
        var l = a.Line;
        var std = LeadTimes.StandardTransitDays(l.SupplierTransitDays, l.CountryCode, l.DefaultTransitDays, set);
        var clearing = l.Status switch
        {
            SupplyStatus.Delivered => "Cleared",
            SupplyStatus.Customs => l.CustomsStatus ?? "In clearance",
            SupplyStatus.AtPort => "Awaiting clearance",
            SupplyStatus.Shipped => l.Port is null ? "Road — no clearance" : "Not arrived",
            SupplyStatus.Cancelled => "—",
            _ => "Not shipped",
        };
        return new TransitRow(l.Id, l.PoNumber, l.SupplierName, l.SupplierCode, a.Product.CArtSap, a.Product.Description, Mapping.R(l.Quantity),
            a.Product.Unit, Mapping.R(a.Tc), l.CountryName, l.Port, l.Booking, l.BillOfLading, l.Etd, l.Eta, l.ActualArrival, Labels.Of(l.Status),
            l.CustomsStatus, clearing, LeadTimes.EstimatedDelivery(l.Eta, l.ActualArrival, l.Port, set), a.TransitDays, std,
            a.TransitDays is { } t && std is { } sd ? t - sd : null, a.Assessment.DelayDays, Labels.Of(a.Assessment.Level), a.Assessment.Reason);
    }

    private static string Search(TransitRow r) => $"{r.PoNumber} {r.Supplier} {r.SupplierCode} {r.CArtSap} {r.Material} {r.Country} {r.Port} {r.Booking} {r.BillOfLading} {r.Status}";

    private static readonly Dictionary<string, Func<TransitRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["PoNumber"] = r => r.PoNumber,
        ["Supplier"] = r => r.Supplier,
        ["Material"] = r => r.Material,
        ["Country"] = r => r.Country,
        ["Tc"] = r => r.Tc,
        ["Etd"] = r => r.Etd,
        ["Eta"] = r => r.Eta,
        ["ActualArrival"] = r => r.ActualArrival,
        ["EstimatedDelivery"] = r => r.EstimatedDelivery,
        ["Status"] = r => r.Status,
        ["TransitDays"] = r => r.TransitDays,
        ["TransitGapDays"] = r => r.TransitGapDays,
        ["DelayDays"] = r => r.DelayDays,
        ["Risk"] = r => r.Risk switch { "Critical" => 3, "Supply Risk" => 2, "Watch" => 1, _ => 0 },
    };
}

public sealed class SupplierService(IAnalyticsEngine engine)
{
    public const string Window = "Deliveries of the last 12 months + open orders";

    public async Task<SupplierDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var lines = s.FilterLines(filter).ToList();
        var total = SupplierScoring.Score(lines, s.Settings.Supply);
        var rows = Build(s, lines);
        return new SupplierDashboard(s.Period.Info, rows.Count, Mapping.R(total.OnTimePct), Mapping.R(total.AvgDelayDays), total.OpenOrders,
            Mapping.R(total.InTransitTc), Mapping.R(total.AvgTransitDays), total.PartialDeliveries,
            rows.Count(r => r.Risk is "Critical" or "High"), s.Settings.Supply.SupplierOnTimeAlertPct, Window);
    }

    public async Task<IReadOnlyList<SupplierRow>> GetRowsAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        return Build(s, s.FilterLines(filter).ToList());
    }

    private static List<SupplierRow> Build(AnalyticsSnapshot s, List<AssessedLine> lines) =>
        lines.GroupBy(l => l.Line.SupplierCode)
            .Select(g =>
            {
                var first = g.First().Line;
                var sc = SupplierScoring.Score(g.ToList(), s.Settings.Supply);
                var std = LeadTimes.StandardTransitDays(first.SupplierTransitDays, first.CountryCode, first.DefaultTransitDays, s.Settings.Supply);
                return new SupplierRow(g.Key, first.SupplierName, first.CountryName, sc.Orders, sc.Delivered, Mapping.R(sc.OnTimePct),
                    Mapping.R(sc.AvgDelayDays), sc.PartialDeliveries, sc.OpenOrders, Mapping.R(sc.InTransitTc), Mapping.R(sc.AvgTransitDays), std,
                    sc.LateOpen, sc.CriticalOpen, sc.Risk);
            })
            .OrderByDescending(r => r.Risk switch { "Critical" => 3, "High" => 2, "Medium" => 1, _ => 0 })
            .ThenBy(r => r.OnTimePct ?? 100)
            .ToList();
}

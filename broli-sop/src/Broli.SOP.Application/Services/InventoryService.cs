namespace Broli.SOP.Application.Services;

public sealed class InventoryService(IAnalyticsEngine engine, ICurrentUser user)
{
    public async Task<InventoryDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var pos = s.Positions.Values.ToList();

        double Tc(IEnumerable<ProductPosition> ps, Func<ProductPosition, double> q) => Mapping.R(ps.Sum(p => p.Tc(q(p)) ?? 0));
        var withDemand = pos.Where(p => p.AvgConsumption > 0 && p.UnitsPerTc.HasValue).ToList();

        var summary = new InventorySummary(
            Tc(pos, p => p.Opening), Tc(pos, p => p.Receipts), Tc(pos, p => p.Consumption), Tc(pos, p => p.Closing),
            Mapping.R(KpiMath.SafeDivide(withDemand.Sum(p => p.Tc(p.Available) ?? 0), withDemand.Sum(p => p.Tc(p.AvgConsumption) ?? 0))),
            Tc(pos, p => p.SafetyStock), Tc(pos, p => p.Excess),
            pos.Count, pos.Count(p => p.AtRisk), pos.Count(p => p.BelowSafety), pos.Count(p => p.Status == CoverageStatus.Excess),
            finance ? Mapping.R(pos.Sum(p => p.Value(p.Closing) ?? 0)) : null,
            finance ? Mapping.R(pos.Sum(p => p.Value(p.Excess) ?? 0)) : null);

        var months = s.WindowMonths.Skip(1).ToList();
        double? MonthTc(int m, IReadOnlyDictionary<(int, int), double> source)
        {
            double total = 0;
            var any = false;
            foreach (var p in pos)
                if (source.TryGetValue((p.Product.Id, m), out var q)) { total += p.Tc(q) ?? 0; any = true; }
            return any ? Mapping.R(total) : null;
        }

        return new InventoryDashboard(
            s.Period.Info, summary,
            months.Select(PeriodResolver.MonthLabel).ToList(),
            months.Select(m => MonthTc(DateKeys.AddMonths(m, -1), s.Stock)).ToList(),
            months.Select(m => MonthTc(m, s.Receipts) ?? 0).Select(v => (double?)v).ToList(),
            months.Select(m => MonthTc(m, s.Consumption)).ToList(),
            months.Select(m => MonthTc(m, s.Stock)).ToList(),
            ExecutiveService.CoverageDistribution(pos),
            ExecutiveService.StockByCategory(pos),
            Labels.Of(s.Settings.Coverage.Basis),
            s.Settings.Coverage.AverageMonths,
            s.Settings.General.Currency);
    }

    public async Task<PagedResult<InventoryRow>> GetRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, sort, desc);
    }

    public async Task<IReadOnlyList<InventoryRow>> GetAllRowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var (rows, sort, desc) = await RowsAsync(filter, q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, sort, desc).ToList();
    }

    private async Task<(IEnumerable<InventoryRow> Rows, string Sort, bool Desc)> RowsAsync(SopFilter filter, TableQuery q, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        IEnumerable<ProductPosition> pos = s.Positions.Values;
        var view = q.View?.ToLowerInvariant();
        pos = view switch
        {
            "at-risk" => pos.Where(p => p.AtRisk),
            "below-safety" => pos.Where(p => p.BelowSafety),
            "excess" => pos.Where(p => p.Status == CoverageStatus.Excess),
            "coverage" => pos.Where(p => p.Status != CoverageStatus.NoDemand),
            "in-stock" => pos.Where(p => p.Closing > 0),
            null or "" or "all" => pos,
            _ when Labels.TryParse<CoverageStatus>(view, out var st) => pos.Where(p => p.Status == st),
            _ => pos,
        };
        var (sort, desc) = view is "at-risk" or "coverage" or "critical" or "risk" ? ("CoverageMonths", false)
            : view == "excess" ? ("ExcessStock", true)
            : ("ClosingTc", true);
        return (pos.Select(p => p.ToRow(finance)).ToList(), sort, desc);
    }

    private static string Search(InventoryRow r) => $"{r.CArtSap} {r.Description} {r.Category} {r.Brand} {r.MaterialType}";

    private static readonly Dictionary<string, Func<InventoryRow, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CArtSap"] = r => r.CArtSap,
        ["Description"] = r => r.Description,
        ["Category"] = r => r.Category,
        ["Brand"] = r => r.Brand,
        ["OpeningStock"] = r => r.OpeningStock,
        ["Receipts"] = r => r.Receipts,
        ["Consumption"] = r => r.Consumption,
        ["ClosingStock"] = r => r.ClosingStock,
        ["ClosingTc"] = r => r.ClosingTc,
        ["SafetyStock"] = r => r.SafetyStock,
        ["AvgMonthlyConsumption"] = r => r.AvgMonthlyConsumption,
        ["CoverageMonths"] = r => r.CoverageMonths,
        ["CoverageStatus"] = r => r.CoverageStatus,
        ["ExcessStock"] = r => r.ExcessStock,
        ["OpenSupplyQty"] = r => r.OpenSupplyQty,
        ["NextEta"] = r => r.NextEta,
        ["StockoutDate"] = r => r.StockoutDate,
        ["StockValue"] = r => r.StockValue,
    };
}

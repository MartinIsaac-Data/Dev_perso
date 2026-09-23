namespace Broli.SOP.Application.Services;

internal static class Mapping
{
    public static double R(double v) => Math.Round(v, 2);
    public static double? R(double? v) => KpiMath.Finite(v) is { } x ? Math.Round(x, 2) : null;

    public static InventoryRow ToRow(this ProductPosition p, bool finance) => new(
        p.Product.CArtSap,
        p.Product.Description,
        p.Product.CategoryName,
        p.Product.Brand,
        Labels.Of(p.Product.MaterialType),
        p.Product.Unit,
        R(p.Opening),
        R(p.Receipts),
        R(p.Consumption),
        R(p.Closing),
        R(p.Tc(p.Closing)),
        R(p.SafetyStock),
        R(p.AvgConsumption),
        R(p.CoverageMonths),
        Labels.Of(p.Status),
        R(p.Excess),
        p.BelowSafety,
        p.AtRisk,
        R(p.OpenQty),
        R(p.TransitQty),
        p.NextEta,
        p.StockoutDate,
        finance ? R(p.Value(p.Closing)) : null);

    public static SupplyRow ToRow(this AssessedLine a) => new(
        a.Line.Id,
        a.Line.PoNumber,
        a.Product.CArtSap,
        a.Product.Description,
        a.Product.CategoryName,
        a.Line.SupplierName,
        a.Line.SupplierCode,
        a.Line.CountryName,
        R(a.Line.Quantity),
        a.Product.Unit,
        R(a.Tc),
        a.Line.OrderDate,
        a.Line.RequiredDate,
        a.Line.Etd,
        a.Line.Eta,
        a.Line.ActualArrival,
        Labels.Of(a.Line.Status),
        a.Assessment.DelayDays,
        a.TransitDays,
        a.StockoutDate,
        Labels.Of(a.Assessment.Level),
        a.Assessment.Reason,
        a.Line.Port,
        a.Line.Booking,
        a.Line.BillOfLading,
        a.Line.CustomsStatus);

    public static RiskItemDto ToDto(this RiskItem r, DateOnly today)
    {
        var score = (int)r.Impact * (int)Math.Ceiling(Math.Clamp(r.Probability, 0, 100) / 20.0);
        return new RiskItemDto(r.Id, r.Code, Labels.Of(r.Category), r.IsOpportunity, r.Description, r.Product?.CArtSap, r.Product?.Description,
            r.Supplier?.Code, Labels.Of(r.Impact), r.Probability, score, r.Owner, r.Action, r.DueDate, Labels.Of(r.Status),
            r.Status != RiskStatus.Closed && r.DueDate is { } d && d < today);
    }
}

/// <summary>Server-side sorting, searching and paging over in-memory rows.</summary>
internal static class TableHelper
{
    public static PagedResult<T> Page<T>(
        IEnumerable<T> rows,
        TableQuery q,
        IReadOnlyDictionary<string, Func<T, object?>> sortKeys,
        Func<T, string> searchText,
        string? defaultSort = null,
        bool defaultDesc = false)
    {
        var filtered = Filter(rows, q, searchText);
        var sorted = Sort(filtered, q, sortKeys, defaultSort, defaultDesc).ToList();
        var page = q.SafePage;
        var size = q.SafePageSize;
        var items = sorted.Skip((page - 1) * size).Take(size).ToList();
        return new PagedResult<T>(items, sorted.Count, page, size);
    }

    public static IEnumerable<T> Filter<T>(IEnumerable<T> rows, TableQuery q, Func<T, string> searchText)
    {
        if (string.IsNullOrWhiteSpace(q.Search)) return rows;
        var terms = q.Search.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return rows.Where(r =>
        {
            var text = searchText(r);
            return terms.All(t => text.Contains(t, StringComparison.OrdinalIgnoreCase));
        });
    }

    public static IEnumerable<T> Sort<T>(IEnumerable<T> rows, TableQuery q, IReadOnlyDictionary<string, Func<T, object?>> sortKeys, string? defaultSort, bool defaultDesc)
    {
        var (key, desc) = !string.IsNullOrWhiteSpace(q.Sort) && sortKeys.ContainsKey(q.Sort) ? (q.Sort, q.Desc) : (defaultSort, defaultDesc);
        if (key is null || !sortKeys.TryGetValue(key, out var selector)) return rows;
        // Nulls always last, whatever the direction.
        var withValue = rows.Where(r => selector(r) is not null);
        var nulls = rows.Where(r => selector(r) is null);
        var ordered = desc ? withValue.OrderByDescending(selector, Comparer.Instance) : withValue.OrderBy(selector, Comparer.Instance);
        return ordered.Concat(nulls);
    }

    private sealed class Comparer : IComparer<object?>
    {
        public static readonly Comparer Instance = new();
        public int Compare(object? x, object? y) => (x, y) switch
        {
            (string a, string b) => string.Compare(a, b, StringComparison.OrdinalIgnoreCase),
            (IComparable a, _) when y is not null && a.GetType() == y.GetType() => a.CompareTo(y),
            _ => Comparer<object?>.Default.Compare(x?.ToString(), y?.ToString()),
        };
    }
}

internal static class SnapshotQueries
{
    /// <summary>Supply lines narrowed by the filter parts that apply to lines (status, supplier, origin country).</summary>
    public static IEnumerable<AssessedLine> FilterLines(this AnalyticsSnapshot s, SopFilter f)
    {
        IEnumerable<AssessedLine> lines = s.Lines;
        if (f.Statuses.Count > 0)
        {
            var statuses = f.Statuses.Select(x => Labels.TryParse<SupplyStatus>(x, out var st) ? st : (SupplyStatus?)null)
                .Where(x => x.HasValue).Select(x => x!.Value).ToHashSet();
            lines = lines.Where(l => statuses.Contains(l.Line.Status));
        }
        if (f.Suppliers.Count > 0)
        {
            var set = f.Suppliers.ToHashSet(StringComparer.OrdinalIgnoreCase);
            lines = lines.Where(l => set.Contains(l.Line.SupplierCode));
        }
        if (f.Countries.Count > 0)
        {
            var set = f.Countries.ToHashSet(StringComparer.OrdinalIgnoreCase);
            lines = lines.Where(l => l.Line.CountryCode is { } c && set.Contains(c));
        }
        return lines;
    }

    /// <summary>Lines delivered within the given months.</summary>
    public static IEnumerable<AssessedLine> DeliveredIn(this IEnumerable<AssessedLine> lines, IReadOnlyCollection<int> monthKeys) =>
        lines.Where(l => l.Line.Status == SupplyStatus.Delivered && l.Line.ActualArrival is { } a && monthKeys.Contains(DateKeys.MonthKey(a)));

    public static double? OtifPct(this IEnumerable<AssessedLine> delivered, SupplySettings s)
    {
        int total = 0, ok = 0;
        foreach (var l in delivered)
        {
            total++;
            var due = l.Line.RequiredDate ?? l.Line.Eta ?? l.Line.ActualArrival!.Value;
            var onTime = l.Line.ActualArrival!.Value <= due.AddDays(s.OnTimeToleranceDays);
            var inFull = (l.Line.DeliveredQty ?? l.Line.Quantity) >= l.Line.Quantity * s.InFullTolerancePct / 100.0;
            if (onTime && inFull) ok++;
        }
        return total == 0 ? null : KpiMath.Pct(ok, total);
    }

    public static IEnumerable<DemandPoint> DemandIn(this AnalyticsSnapshot s, IReadOnlyCollection<int> monthKeys) =>
        s.Demand.Where(d => monthKeys.Contains(d.MonthKey));

    /// <summary>
    /// Unit for aggregated quantities: the common base unit when every product shares it, otherwise TC.
    /// Returns the converter to apply to each product quantity.
    /// </summary>
    public static (string Unit, Func<int, double, double?> Convert) AggregationUnit(this AnalyticsSnapshot s, IEnumerable<int> productIds)
    {
        var units = productIds.Select(id => s.Positions.TryGetValue(id, out var p) ? p.Product.Unit : null)
            .Where(u => u is not null).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        if (units.Count == 1) return (units[0]!, (_, q) => q);
        return ("TC", (id, q) => s.Positions.TryGetValue(id, out var p) ? p.Tc(q) : null);
    }
}

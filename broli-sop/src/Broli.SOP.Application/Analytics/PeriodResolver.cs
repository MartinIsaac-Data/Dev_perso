using System.Globalization;

namespace Broli.SOP.Application.Analytics;

public record ResolvedPeriod(
    PeriodInfo Info,
    IReadOnlyList<int> MonthKeys,
    IReadOnlyList<int> PreviousMonthKeys,
    int AsOfMonthKey,
    DateOnly AsOfDate)
{
    public int FirstMonthKey => MonthKeys[0];
    public int LastMonthKey => MonthKeys[^1];
}

/// <summary>
/// Turns the Year/Month filter into concrete months. With no month selected, the period is the
/// latest month holding stock data. Stock positions are taken at the last selected month, capped
/// at the latest snapshot (the future has no stock yet).
/// </summary>
public static class PeriodResolver
{
    private static readonly CultureInfo En = CultureInfo.GetCultureInfo("en-US");

    public static ResolvedPeriod Resolve(SopFilter filter, int? latestStockMonthKey, DateOnly today)
    {
        var latest = latestStockMonthKey is { } lk ? DateKeys.FromKey(lk) : DateKeys.MonthStart(today);
        var year = filter.Year is >= 2000 and <= 2100 ? filter.Year.Value : latest.Year;

        var months = filter.Months.Where(m => m is >= 1 and <= 12).Distinct().Order().ToList();
        if (months.Count == 0)
            months.Add(year == latest.Year ? latest.Month : year < latest.Year ? 12 : 1);

        var keys = months.Select(m => DateKeys.MonthKey(year, m)).ToList();
        var latestKey = DateKeys.MonthKey(latest);
        var asOfKey = Math.Min(keys[^1], latestKey);

        var span = (year * 12 + months[^1]) - (year * 12 + months[0]) + 1;
        var previous = keys.Select(k => DateKeys.AddMonths(k, -span)).ToList();

        var asOfMonth = DateKeys.FromKey(asOfKey);
        var asOfDate = asOfMonth.Year == today.Year && asOfMonth.Month == today.Month
            ? today
            : asOfMonth > today ? asOfMonth : DateKeys.MonthEnd(asOfMonth);

        var info = new PeriodInfo(
            Label(year, months),
            year,
            months,
            asOfMonth,
            DateKeys.FromKey(keys[0]),
            DateKeys.MonthEnd(DateKeys.FromKey(keys[^1])),
            Label(previous.Select(DateKeys.FromKey).ToList()));

        return new ResolvedPeriod(info, keys, previous, asOfKey, asOfDate);
    }

    public static string MonthLabel(int monthKey) => DateKeys.FromKey(monthKey).ToString("MMM yy", En);

    private static string Label(int year, IReadOnlyList<int> months) =>
        Label(months.Select(m => new DateOnly(year, m, 1)).ToList());

    private static string Label(IReadOnlyList<DateOnly> months)
    {
        if (months.Count == 0) return "";
        if (months.Count == 1) return months[0].ToString("MMMM yyyy", En);
        var contiguous = months.Zip(months.Skip(1)).All(p => p.First.AddMonths(1) == p.Second);
        if (contiguous)
            return months[0].Year == months[^1].Year
                ? $"{months[0].ToString("MMM", En)} – {months[^1].ToString("MMM yyyy", En)}"
                : $"{months[0].ToString("MMM yyyy", En)} – {months[^1].ToString("MMM yyyy", En)}";
        return string.Join(", ", months.Select(m => m.ToString("MMM", En))) + " " + months[^1].Year;
    }
}

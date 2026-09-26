namespace Broli.SOP.Domain;

/// <summary>Conversions between <see cref="DateOnly"/> and the integer yyyymmdd keys used by fact tables.</summary>
public static class DateKeys
{
    public static int ToKey(DateOnly date) => date.Year * 10000 + date.Month * 100 + date.Day;

    public static int MonthKey(int year, int month) => year * 10000 + month * 100 + 1;

    public static int MonthKey(DateOnly date) => MonthKey(date.Year, date.Month);

    public static DateOnly FromKey(int key) => new(key / 10000, key / 100 % 100, key % 100);

    public static DateOnly MonthStart(DateOnly date) => new(date.Year, date.Month, 1);

    public static DateOnly MonthEnd(DateOnly date) => MonthStart(date).AddMonths(1).AddDays(-1);

    /// <summary>Key of the last day of the month containing <paramref name="monthKey"/>.</summary>
    public static int MonthEndKey(int monthKey) => ToKey(MonthEnd(FromKey(monthKey)));

    public static int AddMonths(int monthKey, int months) => MonthKey(FromKey(monthKey).AddMonths(months));
}

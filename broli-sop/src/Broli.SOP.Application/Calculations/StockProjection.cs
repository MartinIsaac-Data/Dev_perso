using Broli.SOP.Domain;

namespace Broli.SOP.Application.Calculations;

public readonly record struct Arrival(DateOnly Date, double Quantity);

public record ProjectedMonth(int MonthKey, double Opening, double Forecast, double Incoming, double Closing);

/// <summary>
/// Forward stock simulation: on-hand stock is consumed day by day at the forecast rate of
/// each month, and inbound supply is added on its expected date.
/// </summary>
public static class StockProjection
{
    /// <summary>
    /// First day on which stock is exhausted, or null if stock lasts beyond <paramref name="horizonEnd"/>
    /// (or there is no demand). Arrivals dated before <paramref name="from"/> are assumed available on <paramref name="from"/>.
    /// </summary>
    /// <param name="monthlyDemand">Demand for the month starting at the given month key.</param>
    public static DateOnly? FindStockoutDate(
        double startStock,
        DateOnly from,
        DateOnly horizonEnd,
        Func<int, double> monthlyDemand,
        IEnumerable<Arrival> arrivals)
    {
        var ordered = arrivals.Where(a => a.Quantity > 0).OrderBy(a => a.Date).ToList();
        var stock = startStock;
        var next = 0;
        var cachedMonth = -1;
        var daily = 0.0;

        for (var day = from; day <= horizonEnd; day = day.AddDays(1))
        {
            while (next < ordered.Count && ordered[next].Date <= day)
                stock += ordered[next++].Quantity;

            var monthKey = DateKeys.MonthKey(day);
            if (monthKey != cachedMonth)
            {
                cachedMonth = monthKey;
                daily = Math.Max(0, monthlyDemand(monthKey)) / DateTime.DaysInMonth(day.Year, day.Month);
            }

            if (daily <= 0) continue;
            if (stock <= 0) return day;
            stock -= daily;
            if (stock <= 1e-9) return day;
        }
        return null;
    }

    /// <summary>Month-by-month projection starting after the as-of month.</summary>
    public static IReadOnlyList<ProjectedMonth> ProjectMonthly(
        double startStock,
        int asOfMonthKey,
        int months,
        Func<int, double> monthlyDemand,
        IEnumerable<Arrival> arrivals)
    {
        var byMonth = new Dictionary<int, double>();
        var firstKey = DateKeys.AddMonths(asOfMonthKey, 1);
        foreach (var a in arrivals)
        {
            // Anything due up to the end of the as-of month (including overdue) lands in the first projected month.
            var key = Math.Max(DateKeys.MonthKey(a.Date), firstKey);
            byMonth[key] = byMonth.GetValueOrDefault(key) + a.Quantity;
        }

        var result = new List<ProjectedMonth>(months);
        var opening = Math.Max(0, startStock);
        for (var i = 1; i <= months; i++)
        {
            var key = DateKeys.AddMonths(asOfMonthKey, i);
            var demand = Math.Max(0, monthlyDemand(key));
            var incoming = byMonth.GetValueOrDefault(key);
            var closing = Math.Max(0, opening + incoming - demand);
            result.Add(new ProjectedMonth(key, opening, demand, incoming, closing));
            opening = closing;
        }
        return result;
    }
}

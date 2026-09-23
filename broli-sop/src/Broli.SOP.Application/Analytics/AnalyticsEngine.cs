using System.Diagnostics;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Application.Analytics;

public interface IAnalyticsEngine
{
    Task<AnalyticsSnapshot> GetSnapshotAsync(SopFilter filter, CancellationToken ct);
}

/// <summary>
/// Loads pre-aggregated data for a filter and computes every product position once.
/// Results are cached per (data version, day, filter) so 50 users on the same view share one computation.
/// </summary>
public sealed class AnalyticsEngine(
    ISopReadRepository repo,
    ISettingsStore settingsStore,
    IClock clock,
    IDataVersion version,
    IMemoryCache cache,
    ICurrentUser user,
    ILogger<AnalyticsEngine> logger) : IAnalyticsEngine
{
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(10);
    private static readonly SemaphoreSlim BuildLock = new(4);

    public async Task<AnalyticsSnapshot> GetSnapshotAsync(SopFilter filter, CancellationToken ct)
    {
        // Row-level security first: the scoped filter is also the cache key, so users never share out-of-scope data.
        filter = DataScope.Apply(filter, user);
        var key = $"snapshot:{version.Current}:{clock.Today:yyyyMMdd}:{filter.ToQueryString()}";
        if (cache.TryGetValue(key, out AnalyticsSnapshot? cached) && cached is not null) return cached;

        await BuildLock.WaitAsync(ct);
        try
        {
            if (cache.TryGetValue(key, out cached) && cached is not null) return cached;
            var sw = Stopwatch.StartNew();
            var snapshot = await BuildAsync(filter, ct);
            cache.Set(key, snapshot, new MemoryCacheEntryOptions { AbsoluteExpirationRelativeToNow = CacheDuration, Size = 1 });
            logger.LogInformation("Analytics snapshot built in {Elapsed} ms for {Products} products ({Filter})",
                sw.ElapsedMilliseconds, snapshot.Products.Count, filter.ToQueryString());
            return snapshot;
        }
        finally
        {
            BuildLock.Release();
        }
    }

    public static ProductScope ToScope(SopFilter f) => new(
        f.Categories, f.Products, f.Brands, f.Suppliers, f.Countries,
        f.MaterialTypes.Select(m => Enum.TryParse<MaterialType>(m, true, out var t) ? t : (MaterialType?)null)
            .Where(t => t.HasValue).Select(t => t!.Value).ToList());

    private async Task<AnalyticsSnapshot> BuildAsync(SopFilter filter, CancellationToken ct)
    {
        var settings = await settingsStore.GetAsync(ct);
        var today = clock.Today;
        var latest = await repo.GetLatestStockMonthAsync(ct);
        var period = PeriodResolver.Resolve(filter, latest, today);
        var scope = ToScope(filter);

        var asOf = period.AsOfMonthKey;
        var avgMonths = Math.Max(1, settings.Coverage.AverageMonths);
        var horizon = Math.Max(Math.Max(1, settings.Forecast.HorizonMonths), avgMonths);

        var windowStart = DateKeys.AddMonths(asOf, -12);
        var windowMonths = Enumerable.Range(0, 13).Select(i => DateKeys.AddMonths(windowStart, i)).ToList();

        var demandFrom = new[] { windowStart, period.PreviousMonthKeys[0], period.FirstMonthKey }.Min();
        var demandTo = Math.Max(asOf, period.LastMonthKey);
        var deliveredFrom = DateKeys.FromKey(Math.Min(windowStart, period.PreviousMonthKeys[0]));
        var deliveredTo = DateKeys.MonthEnd(DateKeys.FromKey(Math.Max(asOf, period.LastMonthKey)));

        var products = await repo.GetProductsAsync(scope, ct);
        var stockRows = await repo.GetStockByMonthAsync(scope, windowStart, asOf, ct);
        var demandAll = await repo.GetDemandAsync(scope, [], demandFrom, DateKeys.AddMonths(asOf, horizon), ct);
        var demandFiltered = filter.Agencies.Count == 0
            ? demandAll.Where(d => d.MonthKey <= demandTo).ToList()
            : await repo.GetDemandAsync(scope, filter.Agencies, demandFrom, demandTo, ct);
        var forecastRows = await repo.GetForecastAsync(scope, DateKeys.AddMonths(asOf, -1), DateKeys.AddMonths(asOf, horizon), ct);
        var production = await repo.GetProductionAsync(scope, windowStart, Math.Max(asOf, period.LastMonthKey), ct);
        var lines = await repo.GetSupplyLinesAsync(scope, new SupplyWindow(deliveredFrom, deliveredTo), ct);

        var stock = stockRows.ToDictionary(r => (r.ProductId, r.MonthKey), r => r.Quantity);
        var consumption = new Dictionary<(int, int), double>();
        var pastForecast = new Dictionary<(int, int), double>();
        var earliestDemandMonth = int.MaxValue;
        foreach (var d in demandAll)
        {
            consumption[(d.ProductId, d.MonthKey)] = d.Actual;
            pastForecast[(d.ProductId, d.MonthKey)] = d.Forecast;
            if (d.Actual > 0 || d.Forecast > 0) earliestDemandMonth = Math.Min(earliestDemandMonth, d.MonthKey);
        }
        var forecast = forecastRows.ToDictionary(r => (r.ProductId, r.MonthKey), r => r.Quantity);

        var receipts = new Dictionary<(int, int), double>();
        var producedQty = new Dictionary<(int, int), double>();
        foreach (var p in production)
        {
            receipts[(p.ProductId, p.MonthKey)] = receipts.GetValueOrDefault((p.ProductId, p.MonthKey)) + p.Quantity;
            producedQty[(p.ProductId, p.MonthKey)] = producedQty.GetValueOrDefault((p.ProductId, p.MonthKey)) + p.Quantity;
        }
        foreach (var l in lines.Where(l => l.Status == SupplyStatus.Delivered && l.ActualArrival.HasValue))
        {
            var k = (l.ProductId, DateKeys.MonthKey(l.ActualArrival!.Value));
            receipts[k] = receipts.GetValueOrDefault(k) + (l.DeliveredQty ?? l.Quantity);
        }

        double? MonthForecast(int productId, int monthKey) =>
            forecast.TryGetValue((productId, monthKey), out var f) ? f
            : pastForecast.TryGetValue((productId, monthKey), out var pf) ? pf
            : null;

        var productById = products.ToDictionary(p => p.Id);
        var openByProduct = lines.Where(l => l.Status.IsOpen()).GroupBy(l => l.ProductId).ToDictionary(g => g.Key, g => g.ToList());
        var avgByProduct = new Dictionary<int, double>();

        ProductPosition Position(ProductRef p, int monthKey, IReadOnlyList<SupplyLineData> open, DateOnly asOfDate)
        {
            var closing = stock.GetValueOrDefault((p.Id, monthKey));
            var rec = receipts.GetValueOrDefault((p.Id, monthKey));
            var cons = consumption.GetValueOrDefault((p.Id, monthKey));
            var prevKey = DateKeys.AddMonths(monthKey, -1);
            var opening = stock.TryGetValue((p.Id, prevKey), out var prevStock) ? prevStock : Math.Max(0, closing - rec + cons);

            var history = new List<double>();
            for (var i = avgMonths - 1; i >= 0; i--)
            {
                var k = DateKeys.AddMonths(monthKey, -i);
                if (k >= earliestDemandMonth) history.Add(consumption.GetValueOrDefault((p.Id, k)));
            }
            var future = new List<double>();
            for (var i = 1; i <= avgMonths; i++)
                if (MonthForecast(p.Id, DateKeys.AddMonths(monthKey, i)) is { } f) future.Add(f);

            var avg = CoverageCalculator.AverageMonthlyConsumption(settings.Coverage.Basis, history, future);
            var openQty = open.Sum(l => Math.Max(0, l.Quantity - (l.DeliveredQty ?? 0)));
            var transitQty = open.Where(l => l.Status.IsInTransit()).Sum(l => Math.Max(0, l.Quantity - (l.DeliveredQty ?? 0)));
            var available = CoverageCalculator.AvailableStock(closing, transitQty, openQty, settings.Coverage);
            var coverage = CoverageCalculator.CoverageMonths(available, avg);
            var status = CoverageCalculator.Classify(coverage, avg, settings.Coverage);
            var safety = CoverageCalculator.SafetyStock(p.SafetyStockQty, p.CategoryCode, avg, settings.SafetyStock);
            var excess = CoverageCalculator.ExcessStock(available, avg, settings.Coverage);

            DateOnly? stockout = null;
            if (avg > 0)
            {
                var fn = DemandFnFor(p.Id, avg);
                stockout = StockProjection.FindStockoutDate(closing, asOfDate, asOfDate.AddMonths(horizon), fn,
                    open.Select(l => new Arrival(l.Eta ?? l.RequiredDate ?? asOfDate, Math.Max(0, l.Quantity - (l.DeliveredQty ?? 0)))));
            }

            var nextEta = open.Where(l => l.Eta.HasValue).Select(l => l.Eta).Min();
            return new ProductPosition(p, monthKey, opening, rec, cons, closing, available, avg, coverage, status, safety, excess,
                available < safety && avg > 0, CoverageCalculator.IsAtRisk(status), openQty, transitQty, nextEta, stockout,
                TcConverter.UnitsPerTc(p.QtyPerTc, p.Unit, settings.Tc));
        }

        Func<int, double> DemandFnFor(int productId, double fallback) =>
            monthKey => MonthForecast(productId, monthKey) ?? fallback;

        var positions = new Dictionary<int, ProductPosition>(products.Count);
        var previous = new Dictionary<int, ProductPosition>(products.Count);
        var prevKey = DateKeys.AddMonths(asOf, -1);
        foreach (var p in products)
        {
            var open = openByProduct.GetValueOrDefault(p.Id) ?? [];
            var pos = Position(p, asOf, open, period.AsOfDate);
            positions[p.Id] = pos;
            avgByProduct[p.Id] = pos.AvgConsumption;
            previous[p.Id] = Position(p, prevKey, [], DateKeys.MonthEnd(DateKeys.FromKey(prevKey)));
        }

        var assessed = new List<AssessedLine>(lines.Count);
        foreach (var group in lines.GroupBy(l => l.ProductId))
        {
            if (!productById.TryGetValue(group.Key, out var product)) continue;
            var pos = positions[product.Id];
            var fn = DemandFnFor(product.Id, pos.AvgConsumption);
            var unitsPerTc = pos.UnitsPerTc;

            var openSorted = group.Where(l => l.Status.IsOpen())
                .OrderBy(l => l.Eta ?? DateOnly.MaxValue).ThenBy(l => l.Id).ToList();
            var earlier = new List<Arrival>();
            foreach (var line in openSorted)
            {
                DateOnly? stockoutBefore = null;
                if (pos.AvgConsumption > 0 && line.Eta is { } eta)
                    stockoutBefore = StockProjection.FindStockoutDate(pos.Closing, period.AsOfDate, eta.AddDays(1), fn, earlier);
                var a = EtaRiskEngine.Assess(line.Status, line.Eta, line.RequiredDate, line.ActualArrival, stockoutBefore, today,
                    settings.Supply.WatchWindowDays);
                assessed.Add(new AssessedLine(line, product, a, stockoutBefore, line.Containers ?? TcConverter.ToTc(line.Quantity, unitsPerTc),
                    TransitDays(line)));
                if (line.Eta is { } e2) earlier.Add(new Arrival(e2, Math.Max(0, line.Quantity - (line.DeliveredQty ?? 0))));
            }
            foreach (var line in group.Where(l => !l.Status.IsOpen()))
            {
                var a = EtaRiskEngine.Assess(line.Status, line.Eta, line.RequiredDate, line.ActualArrival, null, today, settings.Supply.WatchWindowDays);
                assessed.Add(new AssessedLine(line, product, a, null, line.Containers ?? TcConverter.ToTc(line.Quantity, unitsPerTc), TransitDays(line)));
            }
        }

        return new AnalyticsSnapshot
        {
            Period = period,
            Settings = settings,
            Today = today,
            HasData = latest.HasValue,
            Products = products,
            Positions = positions,
            PreviousPositions = previous,
            WindowMonths = windowMonths,
            Stock = stock,
            Receipts = receipts,
            Consumption = consumption,
            Production = producedQty,
            Demand = demandFiltered,
            Lines = assessed,
            DemandFnFactory = id => DemandFnFor(id, avgByProduct.GetValueOrDefault(id)),
        };
    }

    private static int? TransitDays(SupplyLineData l)
    {
        var arrival = l.ActualArrival ?? l.Eta;
        return l.Etd is { } etd && arrival is { } arr && arr >= etd ? arr.DayNumber - etd.DayNumber : null;
    }
}

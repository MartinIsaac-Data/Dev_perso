namespace Broli.SOP.Application.Services;

public sealed class ProductService(IAnalyticsEngine engine, ISopReadRepository repo, IRiskRepository risks, ICurrentUser user, IClock clock)
{
    /// <summary>Full drill-down for one product, evaluated with the global period filter (product filters ignored).</summary>
    public async Task<ProductDetail?> GetAsync(string cartSap, SopFilter filter, CancellationToken ct)
    {
        var product = await repo.GetProductAsync(cartSap, ct);
        if (product is null) return null;

        var scoped = new SopFilter { Year = filter.Year, Months = filter.Months, Agencies = filter.Agencies, Products = [product.CArtSap] };
        var s = await engine.GetSnapshotAsync(scoped, ct);
        if (!s.Positions.TryGetValue(product.Id, out var pos)) return null;

        var finance = user.Has(Contracts.Security.Permissions.FinanceView);
        var open = s.Lines.Where(l => l.IsOpen && l.Product.Id == product.Id).OrderBy(l => l.Line.Eta ?? DateOnly.MaxValue).ToList();
        var months = s.WindowMonths.Skip(1).ToList();
        var demand = s.Demand.Where(d => d.ProductId == product.Id).ToDictionary(d => d.MonthKey);
        var set = s.Settings;
        var fn = s.DemandFn(product.Id);

        var projection = StockProjection.ProjectMonthly(pos.Closing, s.Period.AsOfMonthKey, Math.Max(1, set.Forecast.HorizonMonths), fn,
                open.Select(l => new Arrival(l.Line.Eta ?? l.Line.RequiredDate ?? s.Period.AsOfDate, l.OpenQuantity)))
            .Select(m =>
            {
                var cov = CoverageCalculator.CoverageMonths(m.Closing, pos.AvgConsumption);
                return new ProjectionMonth(PeriodResolver.MonthLabel(m.MonthKey), Mapping.R(m.Opening), Mapping.R(m.Forecast), Mapping.R(m.Incoming),
                    Mapping.R(m.Closing), Mapping.R(cov), Labels.Of(CoverageCalculator.Classify(cov, pos.AvgConsumption, set.Coverage)));
            })
            .ToList();

        var register = (await risks.ListForProductAsync(product.CArtSap, ct)).Select(r => r.ToDto(clock.Today)).ToList();

        return new ProductDetail(
            s.Period.Info,
            new ProductInfoDto(product.CArtSap, product.Description, product.CategoryName, product.Brand, Labels.Of(product.MaterialType),
                product.Unit, product.MainSupplierName, product.Format, product.Color, product.QtyPerTc, finance ? product.UnitCost : null, product.IsDemo),
            pos.ToRow(finance),
            months.Select(PeriodResolver.MonthLabel).ToList(),
            months.Select(m => s.Stock.TryGetValue((product.Id, m), out var q) ? Mapping.R(q) : (double?)null).ToList(),
            months.Select(m => demand.TryGetValue(m, out var d) ? Mapping.R(d.Actual) : (double?)null).ToList(),
            months.Select(m => demand.TryGetValue(m, out var d) ? Mapping.R(d.Forecast) : (double?)null).ToList(),
            projection,
            open.Select(l => l.ToRow()).ToList(),
            ActionAdvisor.Advise(pos, open, set, s.Today),
            register);
    }
}

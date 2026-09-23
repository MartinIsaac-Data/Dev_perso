namespace Broli.SOP.Data.Repositories;

/// <summary>
/// Analytical queries. Filtering and aggregation run in the database; only per-product,
/// per-month aggregates travel to the application.
/// </summary>
public sealed class SopReadRepository(SopDbContext db) : ISopReadRepository
{
    public async Task<int?> GetLatestStockMonthAsync(CancellationToken ct)
    {
        var max = await db.InventoryFacts.AsNoTracking().MaxAsync(f => (int?)f.DateKey, ct);
        return max is { } k ? DateKeys.MonthKey(DateKeys.FromKey(k)) : null;
    }

    public Task<int?> GetLatestSnapshotDateInMonthAsync(int monthKey, CancellationToken ct) =>
        db.InventoryFacts.AsNoTracking()
            .Where(f => f.DateKey >= monthKey && f.DateKey <= DateKeys.MonthEndKey(monthKey))
            .MaxAsync(f => (int?)f.DateKey, ct);

    public async Task<IReadOnlyList<int>> GetYearsWithDataAsync(CancellationToken ct)
    {
        var inv = await db.InventoryFacts.AsNoTracking().Select(f => f.DateKey / 10000).Distinct().ToListAsync(ct);
        var sales = await db.SalesFacts.AsNoTracking().Select(f => f.DateKey / 10000).Distinct().ToListAsync(ct);
        return inv.Union(sales).Order().ToList();
    }

    private IQueryable<Product> Scoped(ProductScope s)
    {
        IQueryable<Product> q = db.Products.AsNoTracking();
        if (s.Categories.Count > 0) { var v = s.Categories.ToList(); q = q.Where(p => v.Contains(p.Category!.Code)); }
        if (s.Products.Count > 0) { var v = s.Products.ToList(); q = q.Where(p => v.Contains(p.CArtSap)); }
        if (s.Brands.Count > 0) { var v = s.Brands.ToList(); q = q.Where(p => p.Brand != null && v.Contains(p.Brand.Name)); }
        if (s.Suppliers.Count > 0) { var v = s.Suppliers.ToList(); q = q.Where(p => p.MainSupplier != null && v.Contains(p.MainSupplier.Code)); }
        if (s.Countries.Count > 0) { var v = s.Countries.ToList(); q = q.Where(p => p.MainSupplier != null && v.Contains(p.MainSupplier.Country!.Code)); }
        if (s.MaterialTypes.Count > 0) { var v = s.MaterialTypes.ToList(); q = q.Where(p => v.Contains(p.MaterialType)); }
        return q;
    }

    private static bool IsUnscoped(ProductScope s) =>
        s.Categories.Count + s.Products.Count + s.Brands.Count + s.Suppliers.Count + s.Countries.Count + s.MaterialTypes.Count == 0;

    /// <summary>Restricts a fact query to the product scope with an IN (SELECT …) subquery — never a list of ids.</summary>
    private IQueryable<T> InScope<T>(IQueryable<T> facts, ProductScope s, System.Linq.Expressions.Expression<Func<T, int>> productId)
    {
        if (IsUnscoped(s)) return facts;
        var ids = Scoped(s).Select(p => p.Id);
        var param = productId.Parameters[0];
        var contains = System.Linq.Expressions.Expression.Call(typeof(Queryable), nameof(Queryable.Contains), [typeof(int)], ids.Expression, productId.Body);
        return facts.Where(System.Linq.Expressions.Expression.Lambda<Func<T, bool>>(contains, param));
    }

    public async Task<IReadOnlyList<ProductRef>> GetProductsAsync(ProductScope scope, CancellationToken ct) =>
        await Project(Scoped(scope).Where(p => p.IsActive)).ToListAsync(ct);

    public async Task<ProductRef?> GetProductAsync(string cartSap, CancellationToken ct) =>
        await Project(db.Products.AsNoTracking().Where(p => p.CArtSap == cartSap)).FirstOrDefaultAsync(ct);

    private static IQueryable<ProductRef> Project(IQueryable<Product> q) => q.Select(p => new ProductRef(
        p.Id, p.CArtSap, p.Description, p.Category!.Code, p.Category.Name, p.Brand != null ? p.Brand.Name : null, p.MaterialType,
        p.BaseUnit, p.QtyPerTc, p.UnitCost, p.SafetyStockQty,
        p.MainSupplier != null ? p.MainSupplier.Code : null, p.MainSupplier != null ? p.MainSupplier.Name : null,
        p.Format, p.Color, p.IsDemo,
        p.MainSupplier != null ? p.MainSupplier.ProductionLeadDays : null,
        p.MainSupplier != null ? p.MainSupplier.TransitDays : null,
        p.MainSupplier != null ? p.MainSupplier.Country!.Code : null,
        p.MainSupplier != null ? p.MainSupplier.Country!.Name : null,
        p.MainSupplier != null ? p.MainSupplier.Country!.DefaultTransitDays : null));

    public async Task<IReadOnlyList<MonthlyQty>> GetStockByMonthAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct)
    {
        var toKey = DateKeys.MonthEndKey(toMonthKey);
        // The latest snapshot date of each month represents that month.
        var dates = await db.InventoryFacts.AsNoTracking()
            .Where(f => f.DateKey >= fromMonthKey && f.DateKey <= toKey)
            .Select(f => f.DateKey).Distinct().ToListAsync(ct);
        var snapshotKeys = dates.GroupBy(k => k / 100).Select(g => g.Max()).ToList();
        if (snapshotKeys.Count == 0) return [];

        var rows = await InScope(db.InventoryFacts.AsNoTracking().Where(f => snapshotKeys.Contains(f.DateKey)), scope, f => f.ProductId)
            .GroupBy(f => new { f.ProductId, f.DateKey })
            .Select(g => new { g.Key.ProductId, g.Key.DateKey, Qty = g.Sum(x => x.StockQty) })
            .ToListAsync(ct);
        return rows.Select(r => new MonthlyQty(r.ProductId, DateKeys.MonthKey(DateKeys.FromKey(r.DateKey)), r.Qty)).ToList();
    }

    public async Task<IReadOnlyList<DemandPoint>> GetDemandAsync(ProductScope scope, IReadOnlyCollection<string> agencies, int fromMonthKey, int toMonthKey, CancellationToken ct)
    {
        var toKey = DateKeys.MonthEndKey(toMonthKey);
        var q = db.SalesFacts.AsNoTracking().Where(f => f.DateKey >= fromMonthKey && f.DateKey <= toKey);
        if (agencies.Count > 0)
        {
            var v = agencies.ToList();
            q = q.Where(f => v.Contains(f.Agency!.Code));
        }
        var rows = await InScope(q, scope, f => f.ProductId)
            .GroupBy(f => new { f.ProductId, f.DateKey })
            .Select(g => new
            {
                g.Key.ProductId,
                g.Key.DateKey,
                F = g.Sum(x => x.ForecastQty),
                A = g.Sum(x => x.ActualQty),
                O = g.Sum(x => x.OrderedQty),
                HasOrdered = g.Count(x => x.OrderedQty != null),
            })
            .ToListAsync(ct);
        // Several load dates inside one month are summed into that month.
        return rows.GroupBy(r => (r.ProductId, Month: DateKeys.MonthKey(DateKeys.FromKey(r.DateKey))))
            .Select(g => new DemandPoint(g.Key.ProductId, g.Key.Month, g.Sum(x => x.F), g.Sum(x => x.A),
                g.Any(x => x.HasOrdered > 0) ? g.Sum(x => x.O ?? 0) : null))
            .ToList();
    }

    public async Task<IReadOnlyList<MonthlyQty>> GetForecastAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct)
    {
        var toKey = DateKeys.MonthEndKey(toMonthKey);
        var rows = await InScope(db.ForecastFacts.AsNoTracking().Where(f => f.DateKey >= fromMonthKey && f.DateKey <= toKey), scope, f => f.ProductId)
            .GroupBy(f => new { f.ProductId, f.DateKey })
            .Select(g => new { g.Key.ProductId, g.Key.DateKey, Qty = g.Sum(x => x.ForecastQty) })
            .ToListAsync(ct);
        return rows.GroupBy(r => (r.ProductId, DateKeys.MonthKey(DateKeys.FromKey(r.DateKey))))
            .Select(g => new MonthlyQty(g.Key.ProductId, g.Key.Item2, g.Sum(x => x.Qty))).ToList();
    }

    public async Task<IReadOnlyList<MonthlyQty>> GetProductionAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct)
    {
        var toKey = DateKeys.MonthEndKey(toMonthKey);
        var rows = await InScope(db.ProductionFacts.AsNoTracking().Where(f => f.DateKey >= fromMonthKey && f.DateKey <= toKey), scope, f => f.ProductId)
            .GroupBy(f => new { f.ProductId, f.DateKey })
            .Select(g => new { g.Key.ProductId, g.Key.DateKey, Qty = g.Sum(x => x.ProducedQty) })
            .ToListAsync(ct);
        return rows.GroupBy(r => (r.ProductId, DateKeys.MonthKey(DateKeys.FromKey(r.DateKey))))
            .Select(g => new MonthlyQty(g.Key.ProductId, g.Key.Item2, g.Sum(x => x.Qty))).ToList();
    }

    public async Task<IReadOnlyList<SupplyLineData>> GetSupplyLinesAsync(ProductScope scope, SupplyWindow window, CancellationToken ct)
    {
        var closed = new[] { SupplyStatus.Delivered, SupplyStatus.Cancelled };
        var from = window.DeliveredFrom;
        var to = window.DeliveredTo;
        var q = db.SupplyLines.AsNoTracking().Where(l =>
            !closed.Contains(l.Status)
            || (l.Status == SupplyStatus.Delivered && l.ActualArrival >= from && l.ActualArrival <= to));
        return await InScope(q, scope, l => l.ProductId)
            .Select(l => new SupplyLineData(
                l.Id, l.PoNumber, l.ProductId, l.Supplier!.Code, l.Supplier.Name,
                l.OriginCountry != null ? l.OriginCountry.Code : l.Supplier.Country!.Code,
                l.OriginCountry != null ? l.OriginCountry.Name : l.Supplier.Country!.Name,
                l.Quantity, l.DeliveredQty, l.Containers, l.OrderDate, l.RequiredDate, l.Etd, l.Eta, l.ActualArrival, l.Status,
                l.Port, l.Booking, l.BillOfLading, l.CustomsStatus,
                l.OriginCountry != null ? l.OriginCountry.DefaultTransitDays : l.Supplier.Country!.DefaultTransitDays,
                l.Supplier.TransitDays))
            .ToListAsync(ct);
    }

    public async Task<FilterOptions> GetFilterOptionsAsync(CancellationToken ct)
    {
        var years = await GetYearsWithDataAsync(ct);
        var latest = await GetLatestStockMonthAsync(ct);
        var latestDate = latest is { } l ? DateKeys.FromKey(l) : (DateOnly?)null;

        var agencies = await db.Agencies.AsNoTracking().OrderBy(a => a.IsInternal).ThenBy(a => a.Name)
            .Select(a => new Option(a.Code, a.Name, a.IsInternal ? "Internal" : "Commercial")).ToListAsync(ct);
        var categories = (await db.Categories.AsNoTracking().OrderBy(c => c.Name).ToListAsync(ct))
            .Select(c => new Option(c.Code, c.Name, Application.Labels.Of(c.MaterialType))).ToList();
        var brands = await db.Brands.AsNoTracking().OrderBy(b => b.Name).Select(b => new Option(b.Name, b.Name, null)).ToListAsync(ct);
        var suppliers = await db.Suppliers.AsNoTracking().OrderBy(s => s.Name)
            .Select(s => new Option(s.Code, s.Name, s.Country!.Name)).ToListAsync(ct);
        var countries = await db.Suppliers.AsNoTracking().Select(s => s.Country!).Distinct().OrderBy(c => c.Name)
            .Select(c => new Option(c.Code, c.Name, null)).ToListAsync(ct);

        return new FilterOptions(
            years.Count > 0 ? years : [DateTime.UtcNow.Year],
            latestDate?.Year, latestDate?.Month,
            agencies, categories, brands, suppliers, countries,
            Enum.GetValues<MaterialType>().Select(m => new Option(m.ToString(), Application.Labels.Of(m))).ToList(),
            Enum.GetValues<SupplyStatus>().Select(s => new Option(s.ToString(), Application.Labels.Of(s))).ToList());
    }

    public async Task<IReadOnlyList<SearchResult>> SearchAsync(string term, int limit, CancellationToken ct)
    {
        var pattern = "%" + term.Replace("[", "[[]").Replace("%", "[%]").Replace("_", "[_]") + "%";
        if (db.Database.IsSqlite()) pattern = "%" + term.Replace("%", "").Replace("_", "") + "%";
        var results = new List<SearchResult>();

        var products = await db.Products.AsNoTracking()
            .Where(p => EF.Functions.Like(p.CArtSap, pattern) || EF.Functions.Like(p.Description, pattern))
            .OrderBy(p => p.CArtSap).Take(limit)
            .Select(p => new { p.CArtSap, p.Description, Category = p.Category!.Name, Brand = p.Brand != null ? p.Brand.Name : null })
            .ToListAsync(ct);
        results.AddRange(products.Select(p => new SearchResult("Product", p.CArtSap, $"{p.CArtSap} · {p.Description}",
            string.Join(" · ", new[] { p.Category, p.Brand }.Where(x => x is not null)), $"/products/{Uri.EscapeDataString(p.CArtSap)}")));

        var suppliers = await db.Suppliers.AsNoTracking()
            .Where(s => EF.Functions.Like(s.Code, pattern) || EF.Functions.Like(s.Name, pattern))
            .OrderBy(s => s.Name).Take(5).Select(s => new { s.Code, s.Name, Country = s.Country!.Name }).ToListAsync(ct);
        results.AddRange(suppliers.Select(s => new SearchResult("Supplier", s.Code, s.Name, $"{s.Code} · {s.Country}",
            $"/supply?view=all&supplier={Uri.EscapeDataString(s.Code)}")));

        var pos = await db.SupplyLines.AsNoTracking()
            .Where(l => EF.Functions.Like(l.PoNumber, pattern))
            .OrderByDescending(l => l.OrderDate).Take(5)
            .Select(l => new { l.PoNumber, Product = l.Product!.Description, l.Status, Supplier = l.Supplier!.Name }).ToListAsync(ct);
        results.AddRange(pos.Select(p => new SearchResult("PO", p.PoNumber, $"PO {p.PoNumber}", $"{p.Product} · {p.Supplier} · {Application.Labels.Of(p.Status)}",
            $"/supply?view=all&search={Uri.EscapeDataString(p.PoNumber)}")));

        var brands = await db.Brands.AsNoTracking().Where(b => EF.Functions.Like(b.Name, pattern)).Take(5).Select(b => b.Name).ToListAsync(ct);
        results.AddRange(brands.Select(b => new SearchResult("Brand", b, b, "Brand — filter all pages", $"/inventory?brand={Uri.EscapeDataString(b)}")));

        var categories = await db.Categories.AsNoTracking().Where(c => EF.Functions.Like(c.Name, pattern) || EF.Functions.Like(c.Code, pattern))
            .Take(5).Select(c => new { c.Code, c.Name, c.MaterialType }).ToListAsync(ct);
        results.AddRange(categories.Select(c => new SearchResult("Material", c.Code, c.Name, $"{Application.Labels.Of(c.MaterialType)} family",
            $"/inventory?category={Uri.EscapeDataString(c.Code)}")));

        return results;
    }

    public async Task<DataStatus> GetDataStatusAsync(CancellationToken ct)
    {
        var counts = new Dictionary<string, int>
        {
            ["Products"] = await db.Products.CountAsync(ct),
            ["Suppliers"] = await db.Suppliers.CountAsync(ct),
            ["FACT_SALES"] = await db.SalesFacts.CountAsync(ct),
            ["FACT_INVENTORY"] = await db.InventoryFacts.CountAsync(ct),
            ["FACT_FORECAST"] = await db.ForecastFacts.CountAsync(ct),
            ["FACT_SUPPLY"] = await db.SupplyLines.CountAsync(ct),
            ["FACT_PRODUCTION"] = await db.ProductionFacts.CountAsync(ct),
            ["Risks"] = await db.RiskItems.CountAsync(ct),
        };
        var latest = await GetLatestStockMonthAsync(ct);
        var lastImport = await db.ImportBatches.Where(b => b.Status == ImportStatus.Committed).MaxAsync(b => (DateTime?)b.UploadedAtUtc, ct);
        return new DataStatus(
            await db.Products.AnyAsync(p => p.IsDemo, ct),
            await db.Products.AnyAsync(p => !p.IsDemo, ct),
            latest is { } l ? DateKeys.FromKey(l) : null,
            lastImport,
            counts);
    }
}

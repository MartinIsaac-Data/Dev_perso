using Broli.SOP.Application.Import;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Data.Repositories;

/// <summary>
/// Writes validated import rows. Every commit runs in one transaction: either the whole file lands, or nothing does.
/// Rows are upserted on their business key, so re-importing a corrected file is safe.
/// </summary>
public sealed class ImportRepository(SopDbContext db, IClock clock, ILogger<ImportRepository> logger) : IImportRepository
{
    public async Task<ImportLookups> GetLookupsAsync(CancellationToken ct)
    {
        var ci = StringComparer.OrdinalIgnoreCase;
        var products = await db.Products.AsNoTracking().Where(p => !p.IsDemo).Select(p => p.CArtSap).ToListAsync(ct);
        var suppliers = await db.Suppliers.AsNoTracking().Where(s => !s.IsDemo).Select(s => new { s.Code, s.Name }).ToListAsync(ct);
        var countries = await db.Countries.AsNoTracking().Select(c => new { c.Code, c.Name }).ToListAsync(ct);
        var categories = await db.Categories.AsNoTracking().Where(c => !c.IsDemo).Select(c => new { c.Code, c.Name }).ToListAsync(ct);
        var agencies = await db.Agencies.AsNoTracking().Where(a => !a.IsDemo).Select(a => new { a.Code, a.Name }).ToListAsync(ct);
        var warehouses = await db.Warehouses.AsNoTracking().Where(w => !w.IsDemo).Select(w => new { w.Code, w.Name }).ToListAsync(ct);

        return new ImportLookups(
            products.ToHashSet(ci),
            suppliers.Select(s => s.Code).ToHashSet(ci),
            suppliers.GroupBy(s => s.Name, ci).ToDictionary(g => g.Key, g => g.First().Code, ci),
            countries.GroupBy(c => c.Name, ci).ToDictionary(g => g.Key, g => g.First().Code, ci),
            countries.Select(c => c.Code).ToHashSet(ci),
            categories.GroupBy(c => c.Name, ci).ToDictionary(g => g.Key, g => g.First().Code, ci),
            categories.Select(c => c.Code).ToHashSet(ci),
            agencies.SelectMany(a => new[] { a.Code, a.Name }).ToHashSet(ci),
            warehouses.SelectMany(w => new[] { w.Code, w.Name }).ToHashSet(ci),
            await db.Products.AnyAsync(p => p.IsDemo, ct));
    }

    public async Task<ImportResult> CommitAsync(ImportType type, string fileName, string username, IReadOnlyList<object> rows, int warningCount,
        bool purgeDemo, CancellationToken ct, string source = "Manual upload")
    {
        var strategy = db.Database.CreateExecutionStrategy();
        return await strategy.ExecuteAsync(async () =>
        {
            await using var tx = await db.Database.BeginTransactionAsync(ct);
            var purged = false;
            if (purgeDemo)
            {
                await PurgeCoreAsync(ct);
                purged = true;
            }

            var batch = new ImportBatch
            {
                Type = type, FileName = fileName, UploadedBy = username, UploadedAtUtc = clock.UtcNow,
                RowCount = rows.Count, WarningCount = warningCount, Status = ImportStatus.Committed, Source = source,
            };
            db.ImportBatches.Add(batch);
            await db.SaveChangesAsync(ct);

            var (inserted, updated) = type switch
            {
                ImportType.SupplierMaster => await Suppliers(rows.Cast<SupplierImportRow>().ToList(), ct),
                ImportType.ProductMaster => await Products(rows.Cast<ProductImportRow>().ToList(), ct),
                ImportType.Sales => await Sales(rows.Cast<SalesImportRow>().ToList(), batch.Id, ct),
                ImportType.Inventory => await Inventory(rows.Cast<InventoryImportRow>().ToList(), batch.Id, ct),
                ImportType.Supply => await Supply(rows.Cast<SupplyImportRow>().ToList(), batch.Id, ct),
                ImportType.Forecast => await Forecast(rows.Cast<ForecastImportRow>().ToList(), batch.Id, ct),
                _ => throw new InvalidOperationException($"Unsupported import type {type}"),
            };
            batch.InsertedCount = inserted;
            batch.UpdatedCount = updated;
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
            db.ChangeTracker.Clear();
            logger.LogInformation("Imported {Type} from {File}: {Inserted} inserted, {Updated} updated", type, fileName, inserted, updated);
            return new ImportResult(batch.Id, type.ToString(), inserted, updated, warningCount, purged);
        });
    }

    private async Task<(int, int)> Suppliers(List<SupplierImportRow> rows, CancellationToken ct)
    {
        var countries = await db.Countries.ToDictionaryAsync(c => c.Code, StringComparer.OrdinalIgnoreCase, ct);
        var existing = await db.Suppliers.ToDictionaryAsync(s => s.Code, StringComparer.OrdinalIgnoreCase, ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            if (!existing.TryGetValue(r.Code, out var s)) { db.Suppliers.Add(s = new Supplier { Code = r.Code }); existing[r.Code] = s; ins++; }
            else upd++;
            s.Name = r.Name;
            s.CountryId = countries[r.CountryCode].Id;
            s.TransitDays = r.TransitDays;
            s.ProductionLeadDays = r.ProductionLeadDays ?? s.ProductionLeadDays;
            s.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<(int, int)> Products(List<ProductImportRow> rows, CancellationToken ct)
    {
        var categories = await db.Categories.ToDictionaryAsync(c => c.Code, StringComparer.OrdinalIgnoreCase, ct);
        foreach (var r in rows.Where(r => r.NewCategoryMaterialType.HasValue && !categories.ContainsKey(r.CategoryCode)))
        {
            var c = new Category { Code = r.CategoryCode, Name = Title(r.CategoryCode), MaterialType = r.NewCategoryMaterialType!.Value };
            db.Categories.Add(c);
            categories[c.Code] = c;
        }
        var brands = await db.Brands.ToDictionaryAsync(b => b.Name, StringComparer.OrdinalIgnoreCase, ct);
        foreach (var name in rows.Select(r => r.Brand).OfType<string>().Distinct(StringComparer.OrdinalIgnoreCase).Where(n => !brands.ContainsKey(n)))
        {
            var b = new Brand { Name = name };
            db.Brands.Add(b);
            brands[name] = b;
        }
        var suppliers = await db.Suppliers.ToDictionaryAsync(s => s.Code, StringComparer.OrdinalIgnoreCase, ct);
        await db.SaveChangesAsync(ct);

        var existing = await db.Products.ToDictionaryAsync(p => p.CArtSap, StringComparer.OrdinalIgnoreCase, ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            if (!existing.TryGetValue(r.CArtSap, out var p)) { db.Products.Add(p = new Product { CArtSap = r.CArtSap }); existing[r.CArtSap] = p; ins++; }
            else upd++;
            var category = categories[r.CategoryCode];
            p.Description = r.Description;
            p.CategoryId = category.Id;
            p.MaterialType = r.NewCategoryMaterialType ?? (r.MaterialType == MaterialType.FinishedGood ? category.MaterialType : r.MaterialType);
            p.BrandId = r.Brand is { } bn ? brands[bn].Id : null;
            p.BaseUnit = r.Unit;
            p.UnitWeightKg = r.UnitWeightKg;
            p.Colisage = r.Colisage;
            p.QtyPerTc = r.QtyPerTc;
            p.UnitCost = r.UnitCost;
            p.SafetyStockQty = r.SafetyStock;
            p.MainSupplierId = r.MainSupplierCode is { } sc ? suppliers[sc].Id : null;
            p.Format = r.Format;
            p.Color = r.Color;
            p.IsActive = true;
            p.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<Dictionary<string, int>> ProductIds(CancellationToken ct) =>
        await db.Products.Where(p => !p.IsDemo).ToDictionaryAsync(p => p.CArtSap, p => p.Id, StringComparer.OrdinalIgnoreCase, ct);

    private async Task<(int, int)> Sales(List<SalesImportRow> rows, int batchId, CancellationToken ct)
    {
        var products = await ProductIds(ct);
        var agencies = await EnsureAgencies(rows.Select(r => r.Agency), ct);
        var months = rows.Select(r => r.MonthKey).Distinct().ToList();
        var existing = await db.SalesFacts.Where(f => months.Contains(f.DateKey))
            .ToDictionaryAsync(f => (f.DateKey, f.ProductId, f.AgencyId), ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            var key = (r.MonthKey, products[r.CArtSap], agencies[r.Agency]);
            if (!existing.TryGetValue(key, out var f))
            {
                db.SalesFacts.Add(f = new SalesFact { DateKey = key.Item1, ProductId = key.Item2, AgencyId = key.Item3 });
                existing[key] = f;
                ins++;
            }
            else upd++;
            f.ForecastQty = r.Forecast;
            f.ActualQty = r.Actual;
            f.OrderedQty = r.Ordered;
            f.ImportBatchId = batchId;
            f.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<(int, int)> Inventory(List<InventoryImportRow> rows, int batchId, CancellationToken ct)
    {
        var products = await ProductIds(ct);
        var warehouses = await EnsureWarehouses(rows.Select(r => r.Warehouse), ct);
        var dates = rows.Select(r => r.DateKey).Distinct().ToList();
        var existing = await db.InventoryFacts.Where(f => dates.Contains(f.DateKey))
            .ToDictionaryAsync(f => (f.DateKey, f.ProductId, f.WarehouseId), ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            var key = (r.DateKey, products[r.CArtSap], warehouses[r.Warehouse]);
            if (!existing.TryGetValue(key, out var f))
            {
                db.InventoryFacts.Add(f = new InventoryFact { DateKey = key.Item1, ProductId = key.Item2, WarehouseId = key.Item3 });
                existing[key] = f;
                ins++;
            }
            else upd++;
            f.StockQty = r.Stock;
            f.ImportBatchId = batchId;
            f.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<(int, int)> Supply(List<SupplyImportRow> rows, int batchId, CancellationToken ct)
    {
        var products = await ProductIds(ct);
        var suppliers = await db.Suppliers.ToDictionaryAsync(s => s.Code, s => s.Id, StringComparer.OrdinalIgnoreCase, ct);
        var countries = await db.Countries.ToDictionaryAsync(c => c.Code, c => c.Id, StringComparer.OrdinalIgnoreCase, ct);
        var pos = rows.Select(r => r.PoNumber).Distinct().ToList();
        var existing = await db.SupplyLines.Where(l => pos.Contains(l.PoNumber)).ToDictionaryAsync(l => (l.PoNumber, l.ProductId), ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            var key = (r.PoNumber, products[r.CArtSap]);
            if (!existing.TryGetValue(key, out var l))
            {
                db.SupplyLines.Add(l = new SupplyLine { PoNumber = r.PoNumber, ProductId = key.Item2 });
                existing[key] = l;
                ins++;
            }
            else upd++;
            l.SupplierId = suppliers[r.SupplierCode];
            l.OriginCountryId = r.CountryCode is { } cc ? countries[cc] : null;
            l.Quantity = r.Quantity;
            l.DeliveredQty = r.DeliveredQty;
            l.Containers = r.Containers;
            l.OrderDate = r.OrderDate;
            l.RequiredDate = r.RequiredDate;
            l.Etd = r.Etd;
            l.Eta = r.Eta;
            l.ActualArrival = r.ActualArrival;
            l.Status = r.Status;
            l.Port = r.Port;
            l.Booking = r.Booking;
            l.BillOfLading = r.BillOfLading;
            l.CustomsStatus = r.CustomsStatus;
            l.ImportBatchId = batchId;
            l.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<(int, int)> Forecast(List<ForecastImportRow> rows, int batchId, CancellationToken ct)
    {
        var products = await ProductIds(ct);
        var months = rows.Select(r => r.MonthKey).Distinct().ToList();
        var existing = await db.ForecastFacts.Where(f => months.Contains(f.DateKey)).ToDictionaryAsync(f => (f.DateKey, f.ProductId), ct);
        int ins = 0, upd = 0;
        foreach (var r in rows)
        {
            var key = (r.MonthKey, products[r.CArtSap]);
            if (!existing.TryGetValue(key, out var f))
            {
                db.ForecastFacts.Add(f = new ForecastFact { DateKey = key.Item1, ProductId = key.Item2 });
                existing[key] = f;
                ins++;
            }
            else upd++;
            f.ForecastQty = r.Forecast;
            f.ImportBatchId = batchId;
            f.IsDemo = false;
        }
        await db.SaveChangesAsync(ct);
        return (ins, upd);
    }

    private async Task<Dictionary<string, int>> EnsureAgencies(IEnumerable<string> names, CancellationToken ct)
    {
        var all = await db.Agencies.Where(a => !a.IsDemo).ToListAsync(ct);
        var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in all) { map[a.Code] = a.Id; map.TryAdd(a.Name, a.Id); }
        foreach (var n in names.Distinct(StringComparer.OrdinalIgnoreCase).Where(n => !map.ContainsKey(n)))
        {
            var a = new Agency { Code = Code(n), Name = n };
            db.Agencies.Add(a);
            await db.SaveChangesAsync(ct);
            map[n] = a.Id;
        }
        return map;
    }

    private async Task<Dictionary<string, int>> EnsureWarehouses(IEnumerable<string> names, CancellationToken ct)
    {
        var all = await db.Warehouses.Where(w => !w.IsDemo).ToListAsync(ct);
        var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var w in all) { map[w.Code] = w.Id; map.TryAdd(w.Name, w.Id); }
        foreach (var n in names.Distinct(StringComparer.OrdinalIgnoreCase).Where(n => !map.ContainsKey(n)))
        {
            var w = new Warehouse { Code = Code(n), Name = n };
            db.Warehouses.Add(w);
            await db.SaveChangesAsync(ct);
            map[n] = w.Id;
        }
        return map;
    }

    private static string Code(string name)
    {
        var c = new string(name.ToUpperInvariant().Select(ch => char.IsLetterOrDigit(ch) ? ch : '_').ToArray()).Trim('_');
        return c.Length > 40 ? c[..40] : c;
    }

    private static string Title(string code) =>
        System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(code.Replace('_', ' ').ToLowerInvariant());

    public async Task RecordRejectedAsync(ImportType type, string fileName, string source, int rowCount, int errors, int warnings, string message,
        ImportStatus status, CancellationToken ct)
    {
        db.ImportBatches.Add(new ImportBatch
        {
            Type = type, FileName = fileName, UploadedBy = "scheduler", UploadedAtUtc = clock.UtcNow, RowCount = rowCount, ErrorCount = errors,
            WarningCount = warnings, Status = status, Source = source, Message = message.Length > 2000 ? message[..1999] + "…" : message,
        });
        await db.SaveChangesAsync(ct);
    }

    public async Task<IReadOnlyList<ImportBatch>> ListBatchesAsync(int limit, CancellationToken ct) =>
        await db.ImportBatches.AsNoTracking().OrderByDescending(b => b.Id).Take(limit).ToListAsync(ct);

    public async Task<int> PurgeDemoDataAsync(CancellationToken ct)
    {
        var strategy = db.Database.CreateExecutionStrategy();
        return await strategy.ExecuteAsync(async () =>
        {
            await using var tx = await db.Database.BeginTransactionAsync(ct);
            var n = await PurgeCoreAsync(ct);
            await tx.CommitAsync(ct);
            return n;
        });
    }

    /// <summary>Deletes every DEMO row, children first. Reference data (countries, roles, calendar) is kept.</summary>
    private async Task<int> PurgeCoreAsync(CancellationToken ct)
    {
        var n = 0;
        n += await db.RiskItems.Where(r => r.IsDemo || (r.Product != null && r.Product.IsDemo) || (r.Supplier != null && r.Supplier.IsDemo)).ExecuteDeleteAsync(ct);
        n += await db.SupplyLines.Where(f => f.IsDemo || f.Product!.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.SalesFacts.Where(f => f.IsDemo || f.Product!.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.InventoryFacts.Where(f => f.IsDemo || f.Product!.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.ForecastFacts.Where(f => f.IsDemo || f.Product!.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.ProductionFacts.Where(f => f.IsDemo || f.Product!.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Products.Where(p => p.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Suppliers.Where(s => s.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Categories.Where(c => c.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Brands.Where(b => b.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Customers.Where(c => c.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Agencies.Where(a => a.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Warehouses.Where(w => w.IsDemo).ExecuteDeleteAsync(ct);
        n += await db.Users.Where(u => u.IsDemo).ExecuteDeleteAsync(ct);
        logger.LogWarning("Purged {Rows} DEMO rows", n);
        return n;
    }
}

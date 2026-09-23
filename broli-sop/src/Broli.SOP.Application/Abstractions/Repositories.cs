using Broli.SOP.Application.Analytics;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Domain.Entities;
using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Application.Abstractions;

/// <summary>
/// Read side of the analytical model. This is the seam that lets the source change
/// (Excel imports today, SQL Server / ERP later) without touching business logic or UI.
/// All methods return pre-aggregated data — never whole tables.
/// </summary>
public interface ISopReadRepository
{
    /// <summary>Month key (yyyymm01) of the most recent stock snapshot, or null when there is no stock data.</summary>
    Task<int?> GetLatestStockMonthAsync(CancellationToken ct);
    /// <summary>Most recent snapshot date key within a month.</summary>
    Task<int?> GetLatestSnapshotDateInMonthAsync(int monthKey, CancellationToken ct);
    Task<IReadOnlyList<int>> GetYearsWithDataAsync(CancellationToken ct);

    Task<IReadOnlyList<ProductRef>> GetProductsAsync(ProductScope scope, CancellationToken ct);
    Task<ProductRef?> GetProductAsync(string cartSap, CancellationToken ct);

    /// <summary>Stock per product and month (latest snapshot in each month, summed over warehouses).</summary>
    Task<IReadOnlyList<MonthlyQty>> GetStockByMonthAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct);

    /// <summary>Demand per product and month, summed over the given agencies (all when empty).</summary>
    Task<IReadOnlyList<DemandPoint>> GetDemandAsync(ProductScope scope, IReadOnlyCollection<string> agencies, int fromMonthKey, int toMonthKey, CancellationToken ct);

    Task<IReadOnlyList<MonthlyQty>> GetForecastAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct);
    Task<IReadOnlyList<MonthlyQty>> GetProductionAsync(ProductScope scope, int fromMonthKey, int toMonthKey, CancellationToken ct);
    Task<IReadOnlyList<SupplyLineData>> GetSupplyLinesAsync(ProductScope scope, SupplyWindow window, CancellationToken ct);

    Task<FilterOptions> GetFilterOptionsAsync(CancellationToken ct);
    /// <param name="categories">When not empty, products and families outside these codes are excluded.</param>
    Task<IReadOnlyList<SearchResult>> SearchAsync(string term, int limit, IReadOnlyList<string> categories, CancellationToken ct);
    Task<DataStatus> GetDataStatusAsync(CancellationToken ct);
}

public interface ISupplyRepository
{
    Task<SupplyLine?> FindAsync(long id, CancellationToken ct);
    Task SaveChangesAsync(CancellationToken ct);
}

public interface IRiskRepository
{
    Task<IReadOnlyList<RiskItem>> ListAsync(CancellationToken ct);
    Task<IReadOnlyList<RiskItem>> ListForProductAsync(string cartSap, CancellationToken ct);
    Task<RiskItem?> FindAsync(int id, CancellationToken ct);
    Task<string> NextCodeAsync(CancellationToken ct);
    Task<int?> ProductIdAsync(string cartSap, CancellationToken ct);
    Task<int?> SupplierIdAsync(string code, CancellationToken ct);
    void Add(RiskItem item);
    Task SaveChangesAsync(CancellationToken ct);
}

public interface IUserRepository
{
    Task<AppUser?> FindByUsernameAsync(string username, CancellationToken ct);
    Task<AppUser?> FindAsync(int id, CancellationToken ct);
    Task<IReadOnlyList<AppUser>> ListAsync(CancellationToken ct);
    Task<IReadOnlyList<AppRole>> ListRolesAsync(CancellationToken ct);
    Task<AppRole?> FindRoleAsync(int id, CancellationToken ct);
    Task<IReadOnlyList<AppRole>> FindRolesAsync(IEnumerable<string> names, CancellationToken ct);
    Task<IReadOnlyList<string>> GetPermissionsAsync(int userId, CancellationToken ct);
    void Add(AppUser user);
    void AddRole(AppRole role);
    void RemoveRole(AppRole role);
    Task SaveChangesAsync(CancellationToken ct);
}

public interface IAuditRepository
{
    void Add(AuditEntry entry);
    Task<PagedResult<AuditEntry>> QueryAsync(string? search, string? module, int page, int pageSize, CancellationToken ct);
    Task SaveChangesAsync(CancellationToken ct);
}

/// <summary>Reference data used to validate imports. Only non-DEMO rows count as "known".</summary>
public record ImportLookups(
    IReadOnlySet<string> ProductCodes,
    IReadOnlySet<string> SupplierCodes,
    IReadOnlyDictionary<string, string> SupplierNameToCode,
    IReadOnlyDictionary<string, string> CountryNameToCode,
    IReadOnlySet<string> CountryCodes,
    IReadOnlyDictionary<string, string> CategoryNameToCode,
    IReadOnlySet<string> CategoryCodes,
    IReadOnlySet<string> AgencyNames,
    IReadOnlySet<string> WarehouseNames,
    bool HasDemoData);

public interface IImportRepository
{
    Task<ImportLookups> GetLookupsAsync(CancellationToken ct);
    /// <summary>Writes validated rows atomically; purges DEMO data first when asked.</summary>
    Task<ImportResult> CommitAsync(ImportType type, string fileName, string username, IReadOnlyList<object> rows, int warningCount, bool purgeDemo,
        CancellationToken ct, string source = "Manual upload");
    /// <summary>Records an automated run that was not imported (validation errors or a read failure) in the import history.</summary>
    Task RecordRejectedAsync(ImportType type, string fileName, string source, int rowCount, int errors, int warnings, string message,
        ImportStatus status, CancellationToken ct);
    Task<IReadOnlyList<ImportBatch>> ListBatchesAsync(int limit, CancellationToken ct);
    Task<int> PurgeDemoDataAsync(CancellationToken ct);
}

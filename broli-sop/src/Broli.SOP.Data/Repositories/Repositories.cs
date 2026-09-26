using System.Text.Json;
using Microsoft.Extensions.Caching.Memory;

namespace Broli.SOP.Data.Repositories;

public sealed class SupplyRepository(SopDbContext db) : ISupplyRepository
{
    public Task<SupplyLine?> FindAsync(long id, CancellationToken ct) => db.SupplyLines.FirstOrDefaultAsync(l => l.Id == id, ct);
    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

public sealed class RiskRepository(SopDbContext db) : IRiskRepository
{
    private IQueryable<RiskItem> Items => db.RiskItems.Include(r => r.Product).ThenInclude(p => p!.Category).Include(r => r.Supplier);

    public async Task<IReadOnlyList<RiskItem>> ListAsync(CancellationToken ct) =>
        await Items.AsNoTracking().OrderBy(r => r.Code).ToListAsync(ct);

    public async Task<IReadOnlyList<RiskItem>> ListForProductAsync(string cartSap, CancellationToken ct) =>
        await Items.AsNoTracking().Where(r => r.Product != null && r.Product.CArtSap == cartSap).OrderBy(r => r.Code).ToListAsync(ct);

    public Task<RiskItem?> FindAsync(int id, CancellationToken ct) => Items.FirstOrDefaultAsync(r => r.Id == id, ct);

    public async Task<string> NextCodeAsync(CancellationToken ct)
    {
        var codes = await db.RiskItems.Select(r => r.Code).ToListAsync(ct);
        var max = codes.Select(c => int.TryParse(c.AsSpan(c.IndexOf('-') + 1), out var n) ? n : 0).DefaultIfEmpty(0).Max();
        return $"R-{max + 1:0000}";
    }

    public Task<int?> ProductIdAsync(string cartSap, CancellationToken ct) =>
        db.Products.Where(p => p.CArtSap == cartSap).Select(p => (int?)p.Id).FirstOrDefaultAsync(ct);

    public Task<int?> SupplierIdAsync(string code, CancellationToken ct) =>
        db.Suppliers.Where(s => s.Code == code).Select(s => (int?)s.Id).FirstOrDefaultAsync(ct);

    public void Add(RiskItem item) => db.RiskItems.Add(item);
    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

public sealed class UserRepository(SopDbContext db) : IUserRepository
{
    private IQueryable<AppUser> Users => db.Users.Include(u => u.Roles).ThenInclude(r => r.Role);

    public Task<AppUser?> FindByUsernameAsync(string username, CancellationToken ct)
    {
        var u = username.ToLower();
        return Users.FirstOrDefaultAsync(x => x.Username.ToLower() == u, ct);
    }

    public Task<AppUser?> FindAsync(int id, CancellationToken ct) => Users.FirstOrDefaultAsync(x => x.Id == id, ct);

    public async Task<IReadOnlyList<AppUser>> ListAsync(CancellationToken ct) => await Users.AsNoTracking().ToListAsync(ct);

    public async Task<IReadOnlyList<AppRole>> ListRolesAsync(CancellationToken ct) =>
        await db.Roles.Include(r => r.Permissions).AsNoTracking().ToListAsync(ct);

    public Task<AppRole?> FindRoleAsync(int id, CancellationToken ct) =>
        db.Roles.Include(r => r.Permissions).FirstOrDefaultAsync(r => r.Id == id, ct);

    public async Task<IReadOnlyList<AppRole>> FindRolesAsync(IEnumerable<string> names, CancellationToken ct)
    {
        var upper = names.Select(n => n.Trim().ToUpperInvariant()).ToList();
        return await db.Roles.Where(r => upper.Contains(r.Name)).ToListAsync(ct);
    }

    public async Task<IReadOnlyList<string>> GetPermissionsAsync(int userId, CancellationToken ct) =>
        await db.UserRoles.Where(ur => ur.UserId == userId)
            .SelectMany(ur => ur.Role!.Permissions.Select(p => p.Permission))
            .Distinct().OrderBy(p => p).ToListAsync(ct);

    public void Add(AppUser user) => db.Users.Add(user);
    public void AddRole(AppRole role) => db.Roles.Add(role);
    public void RemoveRole(AppRole role) => db.Roles.Remove(role);
    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

public sealed class AuditRepository(SopDbContext db) : IAuditRepository
{
    public void Add(AuditEntry entry) => db.AuditEntries.Add(entry);

    public async Task<PagedResult<AuditEntry>> QueryAsync(string? search, string? module, int page, int pageSize, CancellationToken ct)
    {
        var q = db.AuditEntries.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(module)) q = q.Where(a => a.Module == module);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var s = $"%{search.Trim()}%";
            q = q.Where(a => EF.Functions.Like(a.Username, s) || EF.Functions.Like(a.Action, s) || EF.Functions.Like(a.ObjectRef!, s)
                             || EF.Functions.Like(a.NewValue!, s) || EF.Functions.Like(a.OldValue!, s));
        }
        var total = await q.CountAsync(ct);
        var items = await q.OrderByDescending(a => a.Id).Skip((page - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<AuditEntry>(items, total, page, pageSize);
    }

    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

/// <summary>Business parameters stored as one JSON document per section, cached until the next save.</summary>
public sealed class SettingsStore(SopDbContext db, IMemoryCache cache, IDataVersion version, IClock clock) : ISettingsStore
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task<SopSettings> GetAsync(CancellationToken ct)
    {
        var key = $"settings:{version.Current}";
        if (cache.TryGetValue(key, out SopSettings? cached) && cached is not null) return cached;

        var rows = await db.Settings.AsNoTracking().ToDictionaryAsync(s => s.Key, s => s.JsonValue, ct);
        T Read<T>(string k) where T : new()
        {
            if (!rows.TryGetValue(k, out var json)) return new T();
            try { return JsonSerializer.Deserialize<T>(json, Json) ?? new T(); }
            catch (JsonException) { return new T(); }
        }
        var settings = new SopSettings(
            Read<CoverageSettings>(CoverageSettings.Key),
            Read<SafetyStockSettings>(SafetyStockSettings.Key),
            Read<ForecastSettings>(ForecastSettings.Key),
            Read<SupplySettings>(SupplySettings.Key),
            Read<TcSettings>(TcSettings.Key),
            Read<GeneralSettings>(GeneralSettings.Key),
            Read<AlertSettings>(AlertSettings.Key));
        cache.Set(key, settings, new MemoryCacheEntryOptions { AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(30), Size = 1 });
        return settings;
    }

    public async Task SaveAsync(SopSettings s, string username, CancellationToken ct)
    {
        await UpsertAsync(CoverageSettings.Key, s.Coverage, username, ct);
        await UpsertAsync(SafetyStockSettings.Key, s.SafetyStock, username, ct);
        await UpsertAsync(ForecastSettings.Key, s.Forecast, username, ct);
        await UpsertAsync(SupplySettings.Key, s.Supply, username, ct);
        await UpsertAsync(TcSettings.Key, s.Tc, username, ct);
        await UpsertAsync(GeneralSettings.Key, s.General, username, ct);
        await UpsertAsync(AlertSettings.Key, s.AlertRules, username, ct);
        await db.SaveChangesAsync(ct);
    }

    private async Task UpsertAsync<T>(string key, T value, string username, CancellationToken ct)
    {
        var json = JsonSerializer.Serialize(value, Json);
        var row = await db.Settings.FirstOrDefaultAsync(x => x.Key == key, ct);
        if (row is null) db.Settings.Add(row = new AppSetting { Key = key });
        if (row.JsonValue == json) return;
        row.JsonValue = json;
        row.UpdatedAtUtc = clock.UtcNow;
        row.UpdatedBy = username;
    }
}

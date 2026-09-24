using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using Broli.SOP.Contracts.Security;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Data.Seeding;

/// <summary>
/// Creates the schema and the minimum reference data. The first administrator comes from configuration
/// (<c>Bootstrap:AdminUsername</c> / <c>Bootstrap:AdminPassword</c>); in Development a random password is
/// generated and written once to the log when none is configured. No credential lives in code.
/// </summary>
public sealed class DatabaseInitializer(
    SopDbContext db,
    IConfiguration config,
    IHostEnvironment env,
    IPasswordHasher hasher,
    IClock clock,
    ILogger<DatabaseInitializer> logger)
{
    /// <summary>Bumped whenever the schema changes. SQLite (dev / demo) databases are checked against it.</summary>
    public const string SchemaVersion = "3";
    private const string SchemaKey = "schemaVersion";

    public async Task InitializeAsync(CancellationToken ct = default)
    {
        if (db.Database.IsSqlServer())
        {
            // Production path: versioned EF Core migrations (Migrations/SqlServer). With Database:ApplyMigrations=false the
            // DBA applies sql/migrations.sql (release package) and the API runs with data rights only; it then refuses a stale schema.
            if (config.GetValue("Database:ApplyMigrations", true))
                await db.Database.MigrateAsync(ct);
            else if ((await db.Database.GetPendingMigrationsAsync(ct)).ToList() is { Count: > 0 } pending)
                throw new InvalidOperationException(
                    $"The SQL Server schema is not up to date: {pending.Count} migration(s) missing ({string.Join(", ", pending)}). " +
                    "Run sql/migrations.sql from this release package on the database, or set Database:ApplyMigrations=true.");
        }
        else
        {
            await EnsureSqliteSchemaAsync(ct);
        }

        await SeedRolesAsync(ct);
        await SeedCountriesAsync(ct);
        await SeedCalendarAsync(ct);
        await SeedSettingsAsync(ct);
        await SeedAdminAsync(ct);

        var demoEnabled = config.GetValue("Demo:Enabled", env.IsDevelopment());
        if (demoEnabled && !await db.Products.AnyAsync(ct) && !await db.ImportBatches.AnyAsync(ct))
        {
            logger.LogInformation("Generating DEMO data…");
            await new DemoDataGenerator(db, clock, config.GetValue("Demo:Seed", 20260923)).GenerateAsync(ct);
            await SeedDemoUsersAsync(ct);
            logger.LogWarning("DEMO data generated. It is flagged IsDemo and removed by the first real master-data import.");
        }
    }

    /// <summary>
    /// SQLite has no migrations here: the schema is created from the model. An older schema holding only DEMO data is
    /// rebuilt automatically; one holding real imports is never touched — start-up stops with an explanation instead.
    /// </summary>
    private async Task EnsureSqliteSchemaAsync(CancellationToken ct)
    {
        if (await db.Database.EnsureCreatedAsync(ct))
        {
            await SetSchemaVersionAsync(ct);
            return;
        }
        string? version = null;
        try { version = await db.Settings.Where(x => x.Key == SchemaKey).Select(x => x.JsonValue).FirstOrDefaultAsync(ct); }
        catch (Exception ex) when (ex is not OperationCanceledException) { logger.LogDebug(ex, "No schema version table"); }
        if (version == $"\"{SchemaVersion}\"") return;

        var hasRealData = false;
        try { hasRealData = await db.ImportBatches.AnyAsync(b => b.Status == ImportStatus.Committed, ct); }
        catch (Exception ex) when (ex is not OperationCanceledException) { logger.LogDebug(ex, "Import history unreadable"); }
        if (hasRealData)
            throw new InvalidOperationException(
                $"The SQLite database was created by an older version (schema {version ?? "1-2"}, expected {SchemaVersion}) and contains imported data. " +
                "Export what you need, then delete the .db file (or move to SQL Server, which uses migrations) and restart.");

        logger.LogWarning("Rebuilding the SQLite demo database for schema version {Version} (it held no imported data).", SchemaVersion);
        await db.Database.EnsureDeletedAsync(ct);
        await db.Database.EnsureCreatedAsync(ct);
        await SetSchemaVersionAsync(ct);
    }

    private async Task SetSchemaVersionAsync(CancellationToken ct)
    {
        db.Settings.Add(new AppSetting { Key = SchemaKey, JsonValue = $"\"{SchemaVersion}\"", UpdatedAtUtc = clock.UtcNow, UpdatedBy = "system" });
        await db.SaveChangesAsync(ct);
    }

    private async Task SeedRolesAsync(CancellationToken ct)
    {
        if (await db.Roles.AnyAsync(ct))
        {
            await SyncSystemRolePermissionsAsync(ct);
            return;
        }
        var descriptions = new Dictionary<string, string>
        {
            ["ADMIN"] = "Users, data, parameters and configuration",
            ["MANAGEMENT"] = "DG / DGA / Direction — executive and strategic views",
            ["SUPPLY"] = "MRP, stock, orders, transit, coverage, forecast, risks",
            ["SALES"] = "Sales, forecast vs actual, service level, stock",
            ["FINANCE"] = "Financial values, costs, stock and financial impacts",
            ["WAREHOUSE"] = "Stock, shelf life, unloading, warehouse situation",
            ["LOGISTICS"] = "Orders, containers, ETD/ETA, port, transit, customs",
            ["PRODUCTION"] = "Raw-material requirements, production, availability",
        };
        foreach (var (name, permissions) in Permissions.DefaultRoles)
        {
            db.Roles.Add(new AppRole
            {
                Name = name,
                Description = descriptions.GetValueOrDefault(name, ""),
                IsSystem = true,
                Permissions = permissions.Select(p => new RolePermission { Permission = p }).ToList(),
            });
        }
        await db.SaveChangesAsync(ct);
        await SyncSystemRolePermissionsAsync(ct);
    }

    /// <summary>
    /// New permissions introduced by an upgrade are granted to the system roles that have them by default,
    /// once (recorded in settings) — later removals by an administrator are respected.
    /// </summary>
    private async Task SyncSystemRolePermissionsAsync(CancellationToken ct)
    {
        const string key = "permissionsSynced";
        var synced = await db.Settings.Where(x => x.Key == key).Select(x => x.JsonValue).FirstOrDefaultAsync(ct);
        var known = synced is null ? [] : System.Text.Json.JsonSerializer.Deserialize<List<string>>(synced) ?? [];
        var all = Permissions.All.Select(p => p.Code).ToList();
        var fresh = all.Except(known).ToList();
        if (fresh.Count == 0) return;
        var roles = await db.Roles.Include(r => r.Permissions).Where(r => r.IsSystem).ToListAsync(ct);
        foreach (var role in roles)
            foreach (var p in fresh.Where(p => Permissions.DefaultRoles.TryGetValue(role.Name, out var d) && d.Contains(p) && role.Permissions.All(x => x.Permission != p)))
                role.Permissions.Add(new RolePermission { Permission = p });
        var row = await db.Settings.FirstOrDefaultAsync(x => x.Key == key, ct);
        if (row is null) db.Settings.Add(row = new AppSetting { Key = key });
        row.JsonValue = System.Text.Json.JsonSerializer.Serialize(all);
        row.UpdatedAtUtc = clock.UtcNow;
        row.UpdatedBy = "system";
        await db.SaveChangesAsync(ct);
    }

    private async Task SeedCountriesAsync(CancellationToken ct)
    {
        var existing = await db.Countries.Select(c => c.Code).ToListAsync(ct);
        foreach (var (code, name, days) in ReferenceData.Countries.Where(c => !existing.Contains(c.Code)))
            db.Countries.Add(new Country { Code = code, Name = name, DefaultTransitDays = days });
        await db.SaveChangesAsync(ct);
    }

    private async Task SeedCalendarAsync(CancellationToken ct)
    {
        if (await db.Dates.AnyAsync(ct)) return;
        var fiscalStart = 1;
        var en = CultureInfo.GetCultureInfo("en-US");
        for (var d = new DateOnly(2020, 1, 1); d <= new DateOnly(2035, 12, 31); d = d.AddDays(1))
        {
            var fp = (d.Month - fiscalStart + 12) % 12 + 1;
            db.Dates.Add(new DateDim
            {
                DateKey = DateKeys.ToKey(d), Date = d, Year = d.Year, Quarter = (d.Month - 1) / 3 + 1, Month = d.Month,
                MonthName = d.ToString("MMMM", en), FiscalYear = fiscalStart == 1 || d.Month < fiscalStart ? d.Year : d.Year + 1,
                FiscalPeriod = fp, IsMonthStart = d.Day == 1,
            });
        }
        await db.SaveChangesAsync(ct);
        db.ChangeTracker.Clear();
    }

    private async Task SeedSettingsAsync(CancellationToken ct)
    {
        var json = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        var defaults = new (string Key, object Value)[]
        {
            (CoverageSettings.Key, new CoverageSettings()),
            (SafetyStockSettings.Key, new SafetyStockSettings()),
            (ForecastSettings.Key, new ForecastSettings()),
            (SupplySettings.Key, new SupplySettings()),
            (TcSettings.Key, new TcSettings()),
            (GeneralSettings.Key, new GeneralSettings()),
            (AlertSettings.Key, new AlertSettings()),
        };
        var existing = await db.Settings.Select(s => s.Key).ToListAsync(ct);
        foreach (var (key, value) in defaults.Where(d => !existing.Contains(d.Key)))
            db.Settings.Add(new AppSetting { Key = key, JsonValue = JsonSerializer.Serialize(value, value.GetType(), json), UpdatedAtUtc = clock.UtcNow, UpdatedBy = "system" });
        await db.SaveChangesAsync(ct);
    }

    private async Task SeedAdminAsync(CancellationToken ct)
    {
        if (await db.Users.AnyAsync(u => !u.IsDemo, ct)) return;

        var username = config["Bootstrap:AdminUsername"] is { Length: > 0 } u ? u : "admin";
        var password = config["Bootstrap:AdminPassword"];
        if (string.IsNullOrEmpty(password))
        {
            if (!env.IsDevelopment())
            {
                logger.LogCritical("No administrator exists and Bootstrap:AdminPassword is not set. Set it (environment variable Bootstrap__AdminPassword) and restart.");
                return;
            }
            password = GeneratePassword();
            logger.LogWarning("Created administrator '{User}' with generated password: {Password}  — change it after first login.", username, password);
        }

        var admin = await db.Roles.FirstAsync(r => r.Name == "ADMIN", ct);
        db.Users.Add(new AppUser
        {
            Username = username,
            DisplayName = "Administrator",
            Department = "IT",
            PasswordHash = hasher.Hash(password),
            CreatedAtUtc = clock.UtcNow,
            Roles = [new UserRole { RoleId = admin.Id }],
        });
        await db.SaveChangesAsync(ct);
    }

    private async Task SeedDemoUsersAsync(CancellationToken ct)
    {
        var password = config["Demo:UserPassword"];
        var generated = string.IsNullOrEmpty(password);
        if (generated) password = GeneratePassword();

        var roles = await db.Roles.ToDictionaryAsync(r => r.Name, ct);
        (string User, string Name, string Dept, string Role)[] demo =
        [
            ("dg", "Directeur Général (DEMO)", "Direction", "MANAGEMENT"),
            ("supply", "Supply Planner (DEMO)", "Supply Chain", "SUPPLY"),
            ("sales", "Sales Manager (DEMO)", "Sales", "SALES"),
            ("finance", "Finance Controller (DEMO)", "Finance", "FINANCE"),
            ("warehouse", "Warehouse Manager (DEMO)", "Warehouse", "WAREHOUSE"),
            ("logistics", "Logistics Officer (DEMO)", "Logistics", "LOGISTICS"),
            ("production", "Production Manager (DEMO)", "Production", "PRODUCTION"),
        ];
        foreach (var d in demo.Where(d => !db.Users.Any(u => u.Username == d.User)))
            db.Users.Add(new AppUser
            {
                Username = d.User, DisplayName = d.Name, Department = d.Dept, IsDemo = true, CreatedAtUtc = clock.UtcNow,
                PasswordHash = hasher.Hash(password!), Roles = [new UserRole { RoleId = roles[d.Role].Id }],
            });
        await db.SaveChangesAsync(ct);
        if (generated)
            logger.LogWarning("DEMO users ({Users}) created with generated password: {Password}", string.Join(", ", demo.Select(d => d.User)), password);
    }

    private static string GeneratePassword() =>
        Convert.ToBase64String(RandomNumberGenerator.GetBytes(12)).Replace('+', 'x').Replace('/', 'y').TrimEnd('=') + "7a";
}

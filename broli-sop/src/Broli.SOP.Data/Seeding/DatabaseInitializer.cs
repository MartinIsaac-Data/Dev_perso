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
    public async Task InitializeAsync(CancellationToken ct = default)
    {
        await db.Database.EnsureCreatedAsync(ct);

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

    private async Task SeedRolesAsync(CancellationToken ct)
    {
        if (await db.Roles.AnyAsync(ct)) return;
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

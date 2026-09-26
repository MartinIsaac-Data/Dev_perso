using Broli.SOP.Data.Repositories;
using Broli.SOP.Data.Seeding;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Broli.SOP.Data;

public static class DependencyInjection
{
    /// <summary>
    /// Registers the data layer. <c>Database:Provider</c> selects "Sqlite" (default) or "SqlServer";
    /// the connection string is <c>ConnectionStrings:Sop</c>. Switching needs no code change.
    /// </summary>
    public static IServiceCollection AddSopData(this IServiceCollection services, IConfiguration config)
    {
        var provider = config["Database:Provider"] ?? "Sqlite";
        var connection = config.GetConnectionString("Sop")
                         ?? (provider.Equals("Sqlite", StringComparison.OrdinalIgnoreCase) ? "Data Source=broli-sop.db" : null)
                         ?? throw new InvalidOperationException("ConnectionStrings:Sop is required for SQL Server.");

        services.AddDbContext<SopDbContext>(o =>
        {
            if (provider.Equals("SqlServer", StringComparison.OrdinalIgnoreCase))
                o.UseSqlServer(connection, sql => sql.EnableRetryOnFailure(3).CommandTimeout(60));
            else if (provider.Equals("Sqlite", StringComparison.OrdinalIgnoreCase))
                o.UseSqlite(connection);
            else
                throw new InvalidOperationException($"Unsupported Database:Provider '{provider}'. Use Sqlite or SqlServer.");
            o.UseQueryTrackingBehavior(QueryTrackingBehavior.TrackAll);
        });

        services.AddScoped<ISopReadRepository, SopReadRepository>();
        services.AddScoped<ISupplyRepository, SupplyRepository>();
        services.AddScoped<IRiskRepository, RiskRepository>();
        services.AddScoped<IUserRepository, UserRepository>();
        services.AddScoped<IAuditRepository, AuditRepository>();
        services.AddScoped<IImportRepository, ImportRepository>();
        services.AddScoped<ISettingsStore, SettingsStore>();
        services.AddScoped<IActionRepository, ActionRepository>();
        services.AddScoped<INotificationRepository, NotificationRepository>();
        services.AddScoped<IDataSourceRepository, DataSourceRepository>();
        services.AddScoped<IReportingRepository, ReportingRepository>();
        services.AddScoped<IDataSourceReader, Connectors.DataSourceReader>();
        services.AddScoped<DatabaseInitializer>();
        return services;
    }
}

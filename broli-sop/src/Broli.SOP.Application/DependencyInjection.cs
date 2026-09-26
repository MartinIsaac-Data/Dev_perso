using Broli.SOP.Application.Import;
using Broli.SOP.Application.Services;
using Microsoft.Extensions.DependencyInjection;

namespace Broli.SOP.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddSopApplication(this IServiceCollection services)
    {
        // Entries are weighted by volume (≈ 1 unit per 1 000 rows or 100 products): ~5 000 units ≈ a few hundred MB at most.
        services.AddMemoryCache(o => o.SizeLimit = 5000);
        services.AddScoped<IAnalyticsEngine, AnalyticsEngine>();
        services.AddScoped<ExecutiveService>();
        services.AddScoped<DemandService>();
        services.AddScoped<InventoryService>();
        services.AddScoped<SupplyService>();
        services.AddScoped<RiskService>();
        services.AddScoped<ProductService>();
        services.AddScoped<ReferenceService>();
        services.AddScoped<ExportService>();
        services.AddScoped<AuthService>();
        services.AddScoped<AdminService>();
        services.AddScoped<SettingsService>();
        services.AddScoped<ImportService>();
        services.AddScoped<MrpService>();
        services.AddScoped<MaterialsService>();
        services.AddScoped<TransitService>();
        services.AddScoped<SupplierService>();
        services.AddScoped<ActionService>();
        services.AddScoped<MeetingService>();
        services.AddScoped<NotificationService>();
        services.AddScoped<INotificationPublisher>(sp => sp.GetRequiredService<NotificationService>());
        services.AddScoped<AlertEngine>();
        services.AddScoped<DataRefreshService>();
        services.AddScoped<DataSourceService>();
        services.AddScoped<Reporting.ReportingService>();
        return services;
    }
}

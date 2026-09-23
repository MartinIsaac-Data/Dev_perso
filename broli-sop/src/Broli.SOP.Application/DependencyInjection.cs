using Broli.SOP.Application.Import;
using Broli.SOP.Application.Services;
using Microsoft.Extensions.DependencyInjection;

namespace Broli.SOP.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddSopApplication(this IServiceCollection services)
    {
        services.AddMemoryCache(o => o.SizeLimit = 2000);
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
        return services;
    }
}

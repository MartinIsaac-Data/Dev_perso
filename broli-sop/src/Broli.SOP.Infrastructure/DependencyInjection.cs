using Broli.SOP.Application.Abstractions;
using Microsoft.Extensions.DependencyInjection;

namespace Broli.SOP.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddSopInfrastructure(this IServiceCollection services, JwtOptions jwt)
    {
        services.AddSingleton(jwt);
        services.AddSingleton<IClock, SystemClock>();
        services.AddSingleton<IDataVersion, DataVersion>();
        services.AddSingleton<IPasswordHasher, PasswordHasher>();
        services.AddSingleton<ITokenService, JwtTokenService>();
        services.AddSingleton<IExcelReader, ExcelReader>();
        services.AddSingleton<ITabularExporter, TabularExporter>();
        services.AddScoped<IAuditLogger, AuditLogger>();
        services.AddSingleton<IEmailSender, SmtpEmailSender>();
        return services;
    }
}

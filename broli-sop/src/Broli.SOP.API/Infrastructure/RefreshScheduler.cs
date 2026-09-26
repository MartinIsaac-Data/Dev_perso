using Broli.SOP.Application.Abstractions;
using Broli.SOP.Application.Import;
using Broli.SOP.Application.Services;
using Broli.SOP.Contracts.Dtos;

namespace Broli.SOP.API.Infrastructure;

/// <summary>
/// Automated data refresh. Every minute: runs data sources whose daily time has come, then (once a day at
/// <c>Refresh:AlertsAt</c>) evaluates the alert rules. Disable with <c>Refresh:Enabled=false</c>.
/// Runs as the system actor "scheduler" (full rights, no data scope) and is audited.
/// With several API instances, enable it on one instance only.
/// </summary>
public sealed class RefreshScheduler(IServiceScopeFactory scopes, IConfiguration config, ILogger<RefreshScheduler> logger) : BackgroundService
{
    public bool Enabled => config.GetValue("Refresh:Enabled", true);
    public IReadOnlyList<DataSourceRunResult> LastRun { get; private set; } = [];
    private DateOnly? _alertsDoneOn;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!Enabled)
        {
            logger.LogInformation("Automated refresh is disabled (Refresh:Enabled=false).");
            return;
        }
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(config.GetValue("Refresh:PollSeconds", 60)));
        do
        {
            try { await TickAsync(DateTime.Now, stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { return; }
            catch (Exception ex) { logger.LogError(ex, "Scheduled refresh failed"); }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    public async Task TickAsync(DateTime localNow, CancellationToken ct)
    {
        await SystemActor.Run("scheduler", async () =>
        {
            using var scope = scopes.CreateScope();
            var refresh = scope.ServiceProvider.GetRequiredService<DataRefreshService>();
            var results = await refresh.RunDueAsync(localNow, ct);
            if (results.Count > 0)
            {
                LastRun = results;
                logger.LogInformation("Scheduled refresh: {Summary}", string.Join("; ", results.Select(r => $"{r.Source} {r.Status}")));
            }

            var at = TimeOnly.TryParse(config["Refresh:AlertsAt"] ?? "07:00", out var t) ? t : new TimeOnly(7, 0);
            var today = DateOnly.FromDateTime(localNow);
            if (_alertsDoneOn != today && TimeOnly.FromDateTime(localNow) >= at)
            {
                _alertsDoneOn = today;
                await scope.ServiceProvider.GetRequiredService<AlertEngine>().RunAsync(ct);
            }
            return 0;
        });
    }
}

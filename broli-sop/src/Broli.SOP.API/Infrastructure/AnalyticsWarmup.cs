using Broli.SOP.Application.Abstractions;
using Broli.SOP.Application.Analytics;
using Broli.SOP.Contracts;

namespace Broli.SOP.API.Infrastructure;

/// <summary>
/// Builds the default analytics snapshot at start-up and after every data change (import, refresh, correction),
/// so the first users of the morning do not all wait on the same cold database load. The shared base data it loads
/// serves every filter and every period of the year. Disable with <c>Analytics:WarmUp=false</c>.
/// </summary>
public sealed class AnalyticsWarmup(IServiceScopeFactory scopes, IDataVersion version, IHostApplicationLifetime lifetime,
    IConfiguration config, ILogger<AnalyticsWarmup> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!config.GetValue("Analytics:WarmUp", true)) return;
        using (var started = CancellationTokenSource.CreateLinkedTokenSource(lifetime.ApplicationStarted, stoppingToken))
            try { await Task.Delay(Timeout.Infinite, started.Token); } catch (OperationCanceledException) { }
        if (stoppingToken.IsCancellationRequested) return;

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(Math.Max(5, config.GetValue("Analytics:WarmUpPollSeconds", 30))));
        long? warmed = null;
        do
        {
            var current = version.Current;
            if (warmed == current) continue;
            try
            {
                await SystemActor.Run("warmup", async () =>
                {
                    using var scope = scopes.CreateScope();
                    await scope.ServiceProvider.GetRequiredService<IAnalyticsEngine>().GetSnapshotAsync(new SopFilter(), stoppingToken);
                    return 0;
                });
                warmed = current;
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { return; }
            catch (Exception ex) { logger.LogWarning(ex, "Analytics warm-up failed; the next request will build the snapshot"); }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }
}

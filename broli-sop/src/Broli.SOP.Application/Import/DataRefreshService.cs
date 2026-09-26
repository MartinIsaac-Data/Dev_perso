using Microsoft.Extensions.Logging;
using Broli.SOP.Application.Services;

namespace Broli.SOP.Application.Import;

/// <summary>
/// Automated refresh: reads each data source (ERP staging table, Excel inbox folder) and pushes it through the
/// exact same validation and transactional load as a manual upload. A source with any error is rejected as a whole,
/// recorded in the import history and reported to the data administrators — invalid data is never loaded silently.
/// </summary>
public sealed class DataRefreshService(
    IDataSourceRepository sources,
    IDataSourceReader reader,
    IImportRepository imports,
    ImportService importService,
    NotificationService notifications,
    AlertEngine alerts,
    ISettingsStore settings,
    IAuditLogger audit,
    IDataVersion version,
    IClock clock,
    ILogger<DataRefreshService> logger)
{
    /// <summary>Masters first, so facts always find their products and suppliers.</summary>
    public static readonly ImportType[] LoadOrder =
        [ImportType.SupplierMaster, ImportType.ProductMaster, ImportType.Inventory, ImportType.Sales, ImportType.Forecast, ImportType.Supply];

    public RefreshInfo Info(bool schedulerEnabled, IReadOnlyList<DataSourceRunResult> lastRun) =>
        new(schedulerEnabled, reader.InboxRoot, reader.ConnectionNames, lastRun);

    public async Task<IReadOnlyList<DataSourceRunResult>> RunAsync(int id, CancellationToken ct)
    {
        var source = await sources.FindAsync(id, ct) ?? throw new Services.ValidationException([$"Source de données {id} introuvable."]);
        var results = await RunSourceAsync(source, ct);
        if (results.Any(r => r.Status == "Imported")) await alerts.RunAsync(ct);
        return results;
    }

    /// <summary>Runs every enabled source whose daily time has passed today and which has not run yet today.</summary>
    public async Task<IReadOnlyList<DataSourceRunResult>> RunDueAsync(DateTime localNow, CancellationToken ct)
    {
        var due = (await sources.ListAsync(ct)).Where(s => s.Enabled && IsDue(s, localNow)).ToList();
        return await RunManyAsync(due, ct);
    }

    public async Task<IReadOnlyList<DataSourceRunResult>> RunAllAsync(CancellationToken ct) =>
        await RunManyAsync((await sources.ListAsync(ct)).Where(s => s.Enabled).ToList(), ct);

    public static bool IsDue(DataSource s, DateTime localNow)
    {
        if (!TimeOnly.TryParseExact(s.DailyAt, "HH:mm", out var at)) return false;
        if (TimeOnly.FromDateTime(localNow) < at) return false;
        return s.LastRunUtc is null || s.LastRunUtc.Value.ToLocalTime().Date < localNow.Date;
    }

    private async Task<IReadOnlyList<DataSourceRunResult>> RunManyAsync(List<DataSource> list, CancellationToken ct)
    {
        var results = new List<DataSourceRunResult>();
        foreach (var s in list.OrderBy(s => Array.IndexOf(LoadOrder, s.ImportType)).ThenBy(s => s.Name))
            results.AddRange(await RunSourceAsync(s, ct));
        if (results.Any(r => r.Status == "Imported")) await alerts.RunAsync(ct);
        return results;
    }

    private async Task<IReadOnlyList<DataSourceRunResult>> RunSourceAsync(DataSource source, CancellationToken ct)
    {
        var def = ImportDefinitions.Get(source.ImportType);
        var results = new List<DataSourceRunResult>();
        IReadOnlyList<SourcePayload> payloads;
        try
        {
            payloads = await reader.ReadAsync(source, ct);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogError(ex, "Data source {Source} could not be read", source.Name);
            var msg = $"Échec de lecture : {ex.Message}";
            await imports.RecordRejectedAsync(source.ImportType, source.Location, source.Name, 0, 1, 0, msg, ImportStatus.Failed, ct);
            await ReportFailureAsync(source, msg, ct);
            results.Add(new DataSourceRunResult(source.Name, "Failed", msg, 0, 1));
            await FinishAsync(source, results, ct);
            return results;
        }

        if (payloads.Count == 0) results.Add(new DataSourceRunResult(source.Name, "No data", "Rien de nouveau à importer.", 0, 0));

        foreach (var payload in payloads)
        {
            var (outcome, purge) = await importService.ValidateAsync(def, payload.Sheet, ct);
            if (!ImportService.CanCommit(outcome))
            {
                var report = string.Join("\n", outcome.Issues.Where(i => i.Severity == "Error").Take(50)
                    .Select(i => $"Ligne {(i.Row == 0 ? "fichier" : i.Row.ToString())} {i.Column} : {i.Message}"));
                if (outcome.ErrorCount == 0) report = "Aucune ligne valide à importer.";
                await imports.RecordRejectedAsync(source.ImportType, payload.Name, source.Name, outcome.RowCount, outcome.ErrorCount, outcome.WarningCount,
                    report, ImportStatus.Rejected, ct);
                await payload.CompleteAsync(false, report);
                await ReportFailureAsync(source, $"{payload.Name} : {outcome.ErrorCount} erreur(s), rien n'a été importé.\n{report}", ct);
                results.Add(new DataSourceRunResult(source.Name, "Rejected", $"{payload.Name} : {outcome.ErrorCount} erreur(s) — rien n'a été importé", outcome.RowCount, outcome.ErrorCount));
                continue;
            }

            var result = await imports.CommitAsync(def.Type, payload.Name, "scheduler", outcome.ValidRows, outcome.WarningCount, purge, ct, source.Name);
            await payload.CompleteAsync(true, null);
            version.Bump();
            await audit.LogAsync("Import automatique", "Gestion des données", $"{source.Name} : {payload.Name}", null,
                $"{result.Inserted} ajoutées, {result.Updated} mises à jour, {result.Warnings} avertissements" + (result.PurgedDemoData ? ", données de DÉMO supprimées" : ""), ct);
            results.Add(new DataSourceRunResult(source.Name, "Imported", $"{payload.Name} : {result.Inserted} ajoutées, {result.Updated} mises à jour", outcome.RowCount, 0));
        }

        await FinishAsync(source, results, ct);
        return results;
    }

    private async Task FinishAsync(DataSource original, List<DataSourceRunResult> results, CancellationToken ct)
    {
        // A committed import clears the unit of work (large loads), which detaches the source: reload it before recording the run.
        var source = await sources.FindAsync(original.Id, ct) ?? original;
        source.LastRunUtc = clock.UtcNow;
        source.LastStatus = results.Any(r => r.Status is "Failed") ? "Failed"
            : results.Any(r => r.Status is "Rejected") ? "Rejected"
            : results.Any(r => r.Status is "Imported") ? "Imported" : "No data";
        var message = string.Join(" | ", results.Select(r => r.Message));
        source.LastMessage = message.Length > 1000 ? message[..999] + "…" : message;
        await sources.SaveChangesAsync(ct);
    }

    private async Task ReportFailureAsync(DataSource source, string message, CancellationToken ct)
    {
        if (!(await settings.GetAsync(ct)).AlertRules.RefreshFailures) return;
        await notifications.NotifyPermissionAsync(Contracts.Security.Permissions.DataImport, "refresh", "critical",
            $"Échec du rafraîchissement : {source.Name}", message, "data", ct);
    }
}

using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Application.Import;

/// <summary>
/// Upload → validation → preview → commit. Validated rows are staged in memory for 30 minutes;
/// a commit is refused while any error remains, so invalid data is never imported silently.
/// </summary>
public sealed class ImportService(
    IExcelReader reader,
    IImportRepository repository,
    ITabularExporter exporter,
    IAuditLogger audit,
    IDataVersion version,
    IMemoryCache cache,
    ILogger<ImportService> logger)
{
    private static readonly TimeSpan StagingDuration = TimeSpan.FromMinutes(30);

    private sealed record Staged(Guid Id, ImportDefinition Definition, string FileName, string Username, ValidationOutcome Outcome, bool PurgeDemo);

    public IReadOnlyList<ImportTemplateInfo> GetTemplates() =>
        ImportDefinitions.All.Select(d => new ImportTemplateInfo(d.Slug, d.Title, d.Description,
            d.RequiredColumns.Select(c => c.Name).ToList(), d.OptionalColumns.Select(c => c.Name).ToList())).ToList();

    public (byte[] Content, string FileName)? GetTemplateFile(string slug)
    {
        var def = ImportDefinitions.Find(slug);
        if (def is null) return null;
        var notes = $"{def.Title}: {def.Description}\nRequired columns: {string.Join(", ", def.RequiredColumns.Select(c => c.Name))}.\n"
                    + "Dates: dd/mm/yyyy or Excel dates. Quantities: numbers ≥ 0. Replace the example row with your data.";
        return (exporter.Template(def.Title, def.RequiredColumns.Select(c => c.Name).ToList(), def.OptionalColumns.Select(c => c.Name).ToList(),
            def.Example, notes), $"template-{def.Slug}.xlsx");
    }

    public async Task<ImportPreview> PreviewAsync(string slug, string fileName, Stream content, string username, CancellationToken ct)
    {
        var def = ImportDefinitions.Find(slug) ?? throw new Services.ValidationException([$"Unknown import type '{slug}'."]);

        RawSheet sheet;
        try
        {
            sheet = reader.Read(content, def.Title);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogWarning(ex, "Unreadable import file {File}", fileName);
            throw new Services.ValidationException([$"The file could not be read as an Excel workbook (.xlsx): {ex.Message}"]);
        }

        var lookups = await repository.GetLookupsAsync(ct);
        var outcome = ImportValidator.Validate(def, sheet, lookups);
        var purge = lookups.HasDemoData && def.Type is ImportType.ProductMaster or ImportType.SupplierMaster;
        var staged = new Staged(Guid.NewGuid(), def, fileName, username, outcome, purge);
        cache.Set(Key(staged.Id), staged, new MemoryCacheEntryOptions { AbsoluteExpirationRelativeToNow = StagingDuration, Size = 1 });

        logger.LogInformation("Import preview {Type} {File}: {Rows} rows, {Errors} errors, {Warnings} warnings",
            def.Slug, fileName, outcome.RowCount, outcome.ErrorCount, outcome.WarningCount);

        return new ImportPreview(staged.Id, def.Slug, fileName, outcome.RowCount, outcome.ValidRows.Count, outcome.Columns, outcome.Samples,
            outcome.Issues.OrderByDescending(i => i.Severity == "Error").ThenBy(i => i.Row).ToList(),
            outcome.ErrorCount, outcome.WarningCount, CanCommit(outcome), purge);
    }

    public async Task<ImportResult> CommitAsync(Guid id, string username, CancellationToken ct)
    {
        if (!cache.TryGetValue(Key(id), out Staged? staged) || staged is null)
            throw new Services.ValidationException(["This preview has expired. Upload the file again."]);
        if (!string.Equals(staged.Username, username, StringComparison.OrdinalIgnoreCase))
            throw new Services.ValidationException(["Only the user who uploaded the file can import it."]);
        if (!CanCommit(staged.Outcome))
            throw new Services.ValidationException([$"The file has {staged.Outcome.ErrorCount} error(s). Fix them and upload again — nothing was imported."]);

        var result = await repository.CommitAsync(staged.Definition.Type, staged.FileName, username, staged.Outcome.ValidRows,
            staged.Outcome.WarningCount, staged.PurgeDemo, ct);
        cache.Remove(Key(id));
        version.Bump();

        if (result.PurgedDemoData)
            await audit.LogAsync("Purged DEMO data", "Data Management", staged.FileName, null, "first real master-data import", ct);
        await audit.LogAsync("Imported file", "Data Management", $"{staged.Definition.Title}: {staged.FileName}", null,
            $"{result.Inserted} inserted, {result.Updated} updated, {result.Warnings} warnings", ct);
        return result;
    }

    public async Task<IReadOnlyList<ImportBatchDto>> GetHistoryAsync(CancellationToken ct) =>
        (await repository.ListBatchesAsync(50, ct)).Select(b => new ImportBatchDto(b.Id, ImportDefinitions.Get(b.Type).Title, b.FileName,
            b.UploadedBy, b.UploadedAtUtc, b.RowCount, b.InsertedCount, b.UpdatedCount, b.WarningCount, b.Status.ToString())).ToList();

    public async Task<int> PurgeDemoAsync(CancellationToken ct)
    {
        var removed = await repository.PurgeDemoDataAsync(ct);
        version.Bump();
        await audit.LogAsync("Purged DEMO data", "Data Management", null, null, $"{removed} rows removed", ct);
        return removed;
    }

    private static bool CanCommit(ValidationOutcome o) => o.ErrorCount == 0 && o.ValidRows.Count > 0;

    private static string Key(Guid id) => $"import:{id}";
}

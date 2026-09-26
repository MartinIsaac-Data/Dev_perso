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
        var notes = $"{def.Title} : {def.Description}\nColonnes obligatoires : {string.Join(", ", def.RequiredColumns.Select(c => c.Name))}.\n"
                    + "Dates : jj/mm/aaaa ou dates Excel. Quantités : nombres ≥ 0. Remplacez la ligne d'exemple par vos données.";
        return (exporter.Template(def.Title, def.RequiredColumns.Select(c => c.Name).ToList(), def.OptionalColumns.Select(c => c.Name).ToList(),
            def.Example, notes), $"template-{def.Slug}.xlsx");
    }

    public async Task<ImportPreview> PreviewAsync(string slug, string fileName, Stream content, string username, CancellationToken ct)
    {
        var def = ImportDefinitions.Find(slug) ?? throw new Services.ValidationException([$"Type d'import inconnu : « {slug} »."]);

        RawSheet sheet;
        try
        {
            sheet = reader.Read(content, def.Title);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogWarning(ex, "Unreadable import file {File}", fileName);
            throw new Services.ValidationException([$"Le fichier n'a pas pu être lu comme un classeur Excel (.xlsx) : {ex.Message}"]);
        }

        var (outcome, purge) = await ValidateAsync(def, sheet, ct);
        var staged = new Staged(Guid.NewGuid(), def, fileName, username, outcome, purge);
        cache.Set(Key(staged.Id), staged, new MemoryCacheEntryOptions { AbsoluteExpirationRelativeToNow = StagingDuration, Size = 1 });

        logger.LogInformation("Import preview {Type} {File}: {Rows} rows, {Errors} errors, {Warnings} warnings",
            def.Slug, fileName, outcome.RowCount, outcome.ErrorCount, outcome.WarningCount);

        return new ImportPreview(staged.Id, def.Slug, fileName, outcome.RowCount, outcome.ValidRows.Count, outcome.Columns, outcome.Samples,
            outcome.Issues.OrderByDescending(i => i.Severity == "Error").ThenBy(i => i.Row).ToList(),
            outcome.ErrorCount, outcome.WarningCount, CanCommit(outcome), purge);
    }

    /// <summary>Validates a sheet against current reference data. Shared by manual uploads and automated sources.</summary>
    public async Task<(ValidationOutcome Outcome, bool PurgeDemo)> ValidateAsync(ImportDefinition def, RawSheet sheet, CancellationToken ct)
    {
        var lookups = await repository.GetLookupsAsync(ct);
        return (ImportValidator.Validate(def, sheet, lookups), lookups.HasDemoData && def.Type is ImportType.ProductMaster or ImportType.SupplierMaster);
    }

    public async Task<ImportResult> CommitAsync(Guid id, string username, CancellationToken ct)
    {
        if (!cache.TryGetValue(Key(id), out Staged? staged) || staged is null)
            throw new Services.ValidationException(["Cet aperçu a expiré. Chargez à nouveau le fichier."]);
        if (!string.Equals(staged.Username, username, StringComparison.OrdinalIgnoreCase))
            throw new Services.ValidationException(["Seul l'utilisateur qui a chargé le fichier peut l'importer."]);
        if (!CanCommit(staged.Outcome))
            throw new Services.ValidationException([$"Le fichier contient {staged.Outcome.ErrorCount} erreur(s). Corrigez-les et chargez-le à nouveau — rien n'a été importé."]);

        var result = await repository.CommitAsync(staged.Definition.Type, staged.FileName, username, staged.Outcome.ValidRows,
            staged.Outcome.WarningCount, staged.PurgeDemo, ct);
        cache.Remove(Key(id));
        version.Bump();

        if (result.PurgedDemoData)
            await audit.LogAsync("Données de DÉMO supprimées", "Gestion des données", staged.FileName, null, "premier import réel du référentiel", ct);
        await audit.LogAsync("Fichier importé", "Gestion des données", $"{staged.Definition.Title} : {staged.FileName}", null,
            $"{result.Inserted} ajoutées, {result.Updated} mises à jour, {result.Warnings} avertissements", ct);
        return result;
    }

    public async Task<IReadOnlyList<ImportBatchDto>> GetHistoryAsync(CancellationToken ct) =>
        (await repository.ListBatchesAsync(50, ct)).Select(b => new ImportBatchDto(b.Id, ImportDefinitions.All.FirstOrDefault(d => d.Type == b.Type)?.Title ?? Labels.Of(b.Type), b.FileName,
            b.UploadedBy, b.UploadedAtUtc, b.RowCount, b.InsertedCount, b.UpdatedCount, b.WarningCount, b.Status.ToString(), b.Source, b.ErrorCount, b.Message)).ToList();

    public async Task<int> PurgeDemoAsync(CancellationToken ct)
    {
        var removed = await repository.PurgeDemoDataAsync(ct);
        version.Bump();
        await audit.LogAsync("Données de DÉMO supprimées", "Gestion des données", null, null, $"{removed} lignes supprimées", ct);
        return removed;
    }

    internal static bool CanCommit(ValidationOutcome o) => o.ErrorCount == 0 && o.ValidRows.Count > 0;

    private static string Key(Guid id) => $"import:{id}";
}

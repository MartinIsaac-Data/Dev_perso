using System.Text.RegularExpressions;
using Broli.SOP.Application.Services;

namespace Broli.SOP.Application.Import;

/// <summary>
/// Administration of automated data sources. Only a table/view identifier or an inbox sub-folder name is stored —
/// never SQL text, file paths or credentials (connection strings stay in server configuration).
/// </summary>
public sealed partial class DataSourceService(IDataSourceRepository repository, IDataSourceReader reader, IAuditLogger audit)
{
    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_]{0,127}(\.[A-Za-z_][A-Za-z0-9_]{0,127})?$")]
    private static partial Regex Identifier();

    [GeneratedRegex(@"^[A-Za-z0-9_\-]{1,64}$")]
    private static partial Regex Folder();

    [GeneratedRegex(@"^([01]\d|2[0-3]):[0-5]\d$")]
    private static partial Regex Time();

    public async Task<IReadOnlyList<DataSourceDto>> ListAsync(CancellationToken ct) =>
        (await repository.ListAsync(ct)).Select(ToDto).ToList();

    public async Task<DataSourceDto> CreateAsync(DataSourceUpsert r, CancellationToken ct)
    {
        var s = new DataSource();
        Apply(s, r, await repository.ListAsync(ct));
        repository.Add(s);
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Source de données créée", "Gestion des données", s.Name, null, Describe(s), ct);
        return ToDto(s);
    }

    public async Task<DataSourceDto?> UpdateAsync(int id, DataSourceUpsert r, CancellationToken ct)
    {
        var s = await repository.FindAsync(id, ct);
        if (s is null) return null;
        var before = Describe(s);
        Apply(s, r, (await repository.ListAsync(ct)).Where(x => x.Id != id).ToList());
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Source de données modifiée", "Gestion des données", s.Name, before, Describe(s), ct);
        return ToDto(s);
    }

    public async Task<bool> DeleteAsync(int id, CancellationToken ct)
    {
        var s = await repository.FindAsync(id, ct);
        if (s is null) return false;
        repository.Remove(s);
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Source de données supprimée", "Gestion des données", s.Name, Describe(s), null, ct);
        return true;
    }

    private void Apply(DataSource s, DataSourceUpsert r, IReadOnlyList<DataSource> others)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(r.Name) || r.Name.Trim().Length > 100) errors.Add("Le nom est obligatoire (100 caractères maximum).");
        else if (others.Any(o => o.Name.Equals(r.Name.Trim(), StringComparison.OrdinalIgnoreCase))) errors.Add($"Une source nommée « {r.Name} » existe déjà.");
        if (!Labels.TryParse<DataSourceKind>(r.Kind, out var kind)) errors.Add($"Type de source inconnu : « {r.Kind} ».");
        var def = ImportDefinitions.Find(r.ImportType);
        if (def is null) errors.Add($"Type d'import inconnu : « {r.ImportType} ».");
        var location = r.Location?.Trim() ?? "";
        if (kind == DataSourceKind.SqlStaging)
        {
            if (!Identifier().IsMatch(location)) errors.Add("La table ou la vue doit être un identifiant simple, par exemple dbo.V_SOP_INVENTORY.");
            if (string.IsNullOrWhiteSpace(r.ConnectionName) || !reader.ConnectionNames.Contains(r.ConnectionName, StringComparer.OrdinalIgnoreCase))
                errors.Add($"Choisissez une connexion configurée sur le serveur ({(reader.ConnectionNames.Count == 0 ? "aucune configurée" : string.Join(", ", reader.ConnectionNames))}).");
        }
        if (kind == DataSourceKind.ExcelFolder)
        {
            if (!Folder().IsMatch(location)) errors.Add("Le dossier doit être un nom simple (lettres, chiffres, - et _), créé sous le dossier de dépôt du serveur.");
            if (reader.InboxRoot is null) errors.Add("Aucun dossier de dépôt n'est configuré sur le serveur (DataSources:InboxRoot).");
        }
        var at = string.IsNullOrWhiteSpace(r.DailyAt) ? null : r.DailyAt.Trim();
        if (at is not null && !Time().IsMatch(at)) errors.Add("L'heure quotidienne doit être au format HH:mm (ex. 06:30), ou vide pour un lancement manuel uniquement.");
        if (errors.Count > 0) throw new ValidationException(errors);

        s.Name = r.Name!.Trim();
        s.Kind = kind;
        s.ImportType = def!.Type;
        s.Location = location;
        s.ConnectionName = kind == DataSourceKind.SqlStaging ? r.ConnectionName!.Trim() : null;
        s.DailyAt = at;
        s.Enabled = r.Enabled;
    }

    private static DataSourceDto ToDto(DataSource s) => new(s.Id, s.Name, s.Kind.ToString(), ImportDefinitions.Get(s.ImportType).Slug, s.Location,
        s.ConnectionName, s.DailyAt, s.Enabled, s.LastRunUtc, s.LastStatus, s.LastMessage);

    private static string Describe(DataSource s) =>
        $"{s.Kind} {ImportDefinitions.Get(s.ImportType).Title} ← {s.ConnectionName}{(s.ConnectionName is null ? "" : ":")}{s.Location} | chaque jour {s.DailyAt ?? "manuel"} | {(s.Enabled ? "active" : "inactive")}";
}

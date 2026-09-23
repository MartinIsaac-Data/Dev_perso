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
        await audit.LogAsync("Created data source", "Data Management", s.Name, null, Describe(s), ct);
        return ToDto(s);
    }

    public async Task<DataSourceDto?> UpdateAsync(int id, DataSourceUpsert r, CancellationToken ct)
    {
        var s = await repository.FindAsync(id, ct);
        if (s is null) return null;
        var before = Describe(s);
        Apply(s, r, (await repository.ListAsync(ct)).Where(x => x.Id != id).ToList());
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Updated data source", "Data Management", s.Name, before, Describe(s), ct);
        return ToDto(s);
    }

    public async Task<bool> DeleteAsync(int id, CancellationToken ct)
    {
        var s = await repository.FindAsync(id, ct);
        if (s is null) return false;
        repository.Remove(s);
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Deleted data source", "Data Management", s.Name, Describe(s), null, ct);
        return true;
    }

    private void Apply(DataSource s, DataSourceUpsert r, IReadOnlyList<DataSource> others)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(r.Name) || r.Name.Trim().Length > 100) errors.Add("Name is required (max 100 characters).");
        else if (others.Any(o => o.Name.Equals(r.Name.Trim(), StringComparison.OrdinalIgnoreCase))) errors.Add($"A source named '{r.Name}' already exists.");
        if (!Labels.TryParse<DataSourceKind>(r.Kind, out var kind)) errors.Add($"Unknown kind '{r.Kind}'.");
        var def = ImportDefinitions.Find(r.ImportType);
        if (def is null) errors.Add($"Unknown import type '{r.ImportType}'.");
        var location = r.Location?.Trim() ?? "";
        if (kind == DataSourceKind.SqlStaging)
        {
            if (!Identifier().IsMatch(location)) errors.Add("Table or view must be a plain identifier such as dbo.V_SOP_INVENTORY.");
            if (string.IsNullOrWhiteSpace(r.ConnectionName) || !reader.ConnectionNames.Contains(r.ConnectionName, StringComparer.OrdinalIgnoreCase))
                errors.Add($"Choose a connection configured on the server ({(reader.ConnectionNames.Count == 0 ? "none configured" : string.Join(", ", reader.ConnectionNames))}).");
        }
        if (kind == DataSourceKind.ExcelFolder)
        {
            if (!Folder().IsMatch(location)) errors.Add("Folder must be a simple name (letters, digits, - and _), created under the server inbox.");
            if (reader.InboxRoot is null) errors.Add("The server has no inbox folder configured (DataSources:InboxRoot).");
        }
        var at = string.IsNullOrWhiteSpace(r.DailyAt) ? null : r.DailyAt.Trim();
        if (at is not null && !Time().IsMatch(at)) errors.Add("Daily time must be HH:mm (e.g. 06:30), or empty for manual runs only.");
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
        $"{s.Kind} {ImportDefinitions.Get(s.ImportType).Title} ← {s.ConnectionName}{(s.ConnectionName is null ? "" : ":")}{s.Location} | daily {s.DailyAt ?? "manual"} | {(s.Enabled ? "enabled" : "disabled")}";
}

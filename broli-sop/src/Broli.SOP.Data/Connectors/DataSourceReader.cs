using System.Data.Common;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Data.Connectors;

/// <summary>
/// Reads automated sources into raw sheets for the standard import pipeline.
/// <list type="bullet">
/// <item><b>SqlStaging</b>: <c>SELECT * FROM</c> a table or view of an ERP / staging database. The connection string is taken
/// from configuration by name (<c>ConnectionStrings:{name}</c>); only a validated table/view identifier is stored in the database.
/// Column names follow the Excel templates (aliases accepted).</item>
/// <item><b>ExcelFolder</b>: every .xlsx in <c>{DataSources:InboxRoot}/{sub-folder}</c>; a processed file is moved to
/// <c>processed/</c>, a rejected one to <c>rejected/</c> with an <c>.errors.txt</c> report.</item>
/// </list>
/// </summary>
public sealed partial class DataSourceReader(IConfiguration config, IExcelReader excel, ILogger<DataSourceReader> logger) : IDataSourceReader
{
    public const int MaxRows = 500_000;

    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_]{0,127}(\.[A-Za-z_][A-Za-z0-9_]{0,127})?$")]
    private static partial Regex Identifier();

    [GeneratedRegex(@"^[A-Za-z0-9_\-]{1,64}$")]
    private static partial Regex FolderName();

    public string? InboxRoot => config["DataSources:InboxRoot"];

    public IReadOnlyList<string> ConnectionNames =>
        config.GetSection("ConnectionStrings").GetChildren().Select(c => c.Key).Where(k => !k.Equals("Sop", StringComparison.OrdinalIgnoreCase)).ToList();

    public static bool IsValidIdentifier(string value) => Identifier().IsMatch(value);
    public static bool IsValidFolder(string value) => FolderName().IsMatch(value);

    public Task<IReadOnlyList<SourcePayload>> ReadAsync(DataSource source, CancellationToken ct) => source.Kind switch
    {
        DataSourceKind.SqlStaging => ReadSqlAsync(source, ct),
        DataSourceKind.ExcelFolder => Task.FromResult(ReadFolder(source)),
        _ => throw new InvalidOperationException($"Unsupported source kind {source.Kind}."),
    };

    private async Task<IReadOnlyList<SourcePayload>> ReadSqlAsync(DataSource source, CancellationToken ct)
    {
        if (!IsValidIdentifier(source.Location)) throw new InvalidOperationException($"'{source.Location}' is not a valid table or view name.");
        var name = source.ConnectionName ?? throw new InvalidOperationException("No connection name configured for this source.");
        var connectionString = config.GetConnectionString(name) ?? throw new InvalidOperationException($"Connection string '{name}' is not configured on the server.");
        var provider = config[$"DataSources:Connections:{name}:Provider"] ?? "SqlServer";

        await using DbConnection connection = provider.Equals("Sqlite", StringComparison.OrdinalIgnoreCase)
            ? new SqliteConnection(connectionString)
            : new SqlConnection(connectionString);
        await connection.OpenAsync(ct);
        await using var command = connection.CreateCommand();
        command.CommandText = $"SELECT * FROM {Quote(source.Location, provider)}";
        command.CommandTimeout = 300;
        await using var reader = await command.ExecuteReaderAsync(ct);

        var headers = Enumerable.Range(0, reader.FieldCount).Select(reader.GetName).ToList();
        var rows = new List<RawRow>();
        var line = 1;
        while (await reader.ReadAsync(ct))
        {
            line++;
            if (rows.Count >= MaxRows) throw new InvalidOperationException($"More than {MaxRows:N0} rows in {source.Location}.");
            var cells = new object?[headers.Count];
            for (var i = 0; i < headers.Count; i++)
                cells[i] = reader.IsDBNull(i) ? null : Normalize(reader.GetValue(i));
            rows.Add(new RawRow(line, cells));
        }
        logger.LogInformation("Read {Rows} rows from {Table} ({Connection})", rows.Count, source.Location, name);
        var payloadName = $"{name}:{source.Location}";
        return [new SourcePayload(payloadName, new RawSheet(headers, rows), (_, _) => Task.CompletedTask)];
    }

    private static string Quote(string identifier, string provider) =>
        string.Join('.', identifier.Split('.').Select(p => provider.Equals("Sqlite", StringComparison.OrdinalIgnoreCase) ? $"\"{p}\"" : $"[{p}]"));

    /// <summary>Database values → the cell types the validators understand (string, double, DateTime, bool).</summary>
    private static object? Normalize(object value) => value switch
    {
        string s => s,
        DateTime d => d,
        DateOnly d => d.ToDateTime(TimeOnly.MinValue),
        DateTimeOffset d => d.DateTime,
        bool b => b,
        decimal m => (double)m,
        double d => d,
        float f => (double)f,
        long l => (double)l,
        int i => (double)i,
        short s => (double)s,
        byte b => (double)b,
        _ => value.ToString(),
    };

    private IReadOnlyList<SourcePayload> ReadFolder(DataSource source)
    {
        var root = InboxRoot ?? throw new InvalidOperationException("DataSources:InboxRoot is not configured on the server.");
        if (!IsValidFolder(source.Location)) throw new InvalidOperationException($"'{source.Location}' is not a valid folder name.");
        var folder = Path.Combine(root, source.Location);
        Directory.CreateDirectory(folder);
        var payloads = new List<SourcePayload>();
        foreach (var file in Directory.GetFiles(folder, "*.xlsx").Where(f => !Path.GetFileName(f).StartsWith("~$")).Order())
        {
            RawSheet sheet;
            try
            {
                using var stream = File.OpenRead(file);
                sheet = excel.Read(stream, ImportDefinitionsTitle(source.ImportType));
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                logger.LogWarning(ex, "Unreadable file {File}", file);
                Move(file, "rejected", $"The file could not be read as an Excel workbook: {ex.Message}");
                continue;
            }
            var path = file;
            payloads.Add(new SourcePayload(Path.GetFileName(file), sheet, (ok, report) =>
            {
                Move(path, ok ? "processed" : "rejected", report);
                return Task.CompletedTask;
            }));
        }
        return payloads;
    }

    private static string ImportDefinitionsTitle(ImportType type) => Application.Import.ImportDefinitions.Get(type).Title;

    private static void Move(string file, string subFolder, string? report)
    {
        var target = Path.Combine(Path.GetDirectoryName(file)!, subFolder);
        Directory.CreateDirectory(target);
        var name = $"{DateTime.Now:yyyyMMdd-HHmmss}-{Path.GetFileName(file)}";
        File.Move(file, Path.Combine(target, name), overwrite: true);
        if (report is not null) File.WriteAllText(Path.Combine(target, name + ".errors.txt"), report);
    }
}

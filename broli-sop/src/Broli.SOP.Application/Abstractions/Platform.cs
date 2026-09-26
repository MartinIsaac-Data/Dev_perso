using Broli.SOP.Contracts.Settings;

namespace Broli.SOP.Application.Abstractions;

/// <summary>Time source. Injected so calculations and tests are reproducible.</summary>
public interface IClock
{
    DateTime UtcNow { get; }
    DateOnly Today { get; }
}

/// <summary>The authenticated caller, resolved from the request.</summary>
public interface ICurrentUser
{
    string Username { get; }
    bool IsAuthenticated { get; }
    bool Has(string permission);
    /// <summary>Agency codes the user is restricted to; empty = no restriction.</summary>
    IReadOnlyList<string> ScopeAgencies => [];
    /// <summary>Product-family codes the user is restricted to; empty = no restriction.</summary>
    IReadOnlyList<string> ScopeCategories => [];
}

/// <summary>
/// Identity for work that runs outside an HTTP request (scheduled refresh, alert engine).
/// Inside <see cref="Run"/>, <see cref="ICurrentUser"/> resolves to this system actor with full rights and no data scope.
/// </summary>
public static class SystemActor
{
    private static readonly AsyncLocal<string?> Current = new();
    public static string? Name => Current.Value;

    public static async Task<T> Run<T>(string name, Func<Task<T>> work)
    {
        var previous = Current.Value;
        Current.Value = name;
        try { return await work(); }
        finally { Current.Value = previous; }
    }
}

public interface IAuditLogger
{
    Task LogAsync(string action, string module, string? objectRef, string? oldValue, string? newValue, CancellationToken ct = default);
}

/// <summary>Monotonic counter bumped on every data or parameter change. Part of every analytics cache key.</summary>
public interface IDataVersion
{
    long Current { get; }
    void Bump();
}

public interface ISettingsStore
{
    Task<SopSettings> GetAsync(CancellationToken ct = default);
    Task SaveAsync(SopSettings settings, string username, CancellationToken ct = default);
}

public interface IPasswordHasher
{
    string Hash(string password);
    bool Verify(string hash, string password);
}

public record IssuedToken(string Token, DateTime ExpiresAtUtc);

public interface ITokenService
{
    IssuedToken Issue(string username, string displayName, IReadOnlyCollection<string> roles, IReadOnlyCollection<string> permissions,
        IReadOnlyCollection<string>? scopeAgencies = null, IReadOnlyCollection<string>? scopeCategories = null);
}

public record EmailMessage(IReadOnlyList<string> To, string Subject, string Body);

/// <summary>Outbound e-mail. Disabled unless SMTP is configured on the server.</summary>
public interface IEmailSender
{
    bool IsConfigured { get; }
    Task SendAsync(EmailMessage message, CancellationToken ct = default);
}

/// <summary>One worksheet read as raw cells; the header row is already located.</summary>
public record RawSheet(IReadOnlyList<string> Headers, IReadOnlyList<RawRow> Rows);

/// <summary>A data row with its original Excel row number. Cells are string, double, bool, DateTime or null.</summary>
public record RawRow(int ExcelRow, IReadOnlyList<object?> Cells);

public record NamedSheet(string Name, RawSheet Sheet);

public interface IExcelReader
{
    RawSheet Read(Stream stream, string? preferredSheet);

    /// <summary>Every worksheet of the workbook, in order (for multi-sheet files such as the reporting catalogue).</summary>
    IReadOnlyList<NamedSheet> ReadAll(Stream stream);
}

public record TableColumn(string Header, string Format = "text");

/// <summary>A flat table ready to be written to Excel or CSV.</summary>
public record TableData(string Title, string? Subtitle, IReadOnlyList<TableColumn> Columns, IReadOnlyList<object?[]> Rows);

public interface ITabularExporter
{
    byte[] ToXlsx(TableData table);
    byte[] ToCsv(TableData table);
    byte[] Template(string sheetName, IReadOnlyList<string> required, IReadOnlyList<string> optional, IReadOnlyList<object?[]> example, string notes);
}

public record SopNotification(string Kind, string Title, string Message, string? Link, string? Audience);

/// <summary>
/// Outbound notifications (e-mail, in-app, Teams…). Phase 1 only logs; implementations
/// can be added later without touching the business services that raise alerts.
/// </summary>
public interface INotificationPublisher
{
    Task PublishAsync(SopNotification notification, CancellationToken ct = default);
}

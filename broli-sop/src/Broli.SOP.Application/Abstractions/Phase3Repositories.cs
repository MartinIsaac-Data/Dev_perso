namespace Broli.SOP.Application.Abstractions;

public interface IActionRepository
{
    Task<IReadOnlyList<SopAction>> ListAsync(CancellationToken ct);
    Task<SopAction?> FindAsync(int id, CancellationToken ct);
    Task<string> NextCodeAsync(CancellationToken ct);
    Task<int?> RiskIdAsync(string code, CancellationToken ct);
    void Add(SopAction action);
    Task SaveChangesAsync(CancellationToken ct);
}

public record Recipient(int UserId, string Username, string DisplayName, string? Email);

public interface INotificationRepository
{
    Task<IReadOnlyList<Recipient>> RecipientsWithPermissionAsync(string permission, CancellationToken ct);
    Task<Recipient?> FindRecipientAsync(string usernameOrDisplayName, CancellationToken ct);
    Task<int?> UserIdAsync(string username, CancellationToken ct);
    void Add(IEnumerable<Notification> notifications);
    Task<IReadOnlyList<Notification>> ListAsync(int userId, int take, CancellationToken ct);
    Task<int> UnreadCountAsync(int userId, CancellationToken ct);
    Task MarkReadAsync(int userId, long? id, DateTime now, CancellationToken ct);
    /// <summary>Keys of the given alerts raised after <paramref name="since"/>.</summary>
    Task<IReadOnlySet<string>> RecentAlertKeysAsync(IReadOnlyCollection<string> keys, DateTime since, CancellationToken ct);
    Task MarkAlertsRaisedAsync(IReadOnlyCollection<string> keys, DateTime now, CancellationToken ct);
    Task SaveChangesAsync(CancellationToken ct);
}

public interface IDataSourceRepository
{
    Task<IReadOnlyList<DataSource>> ListAsync(CancellationToken ct);
    Task<DataSource?> FindAsync(int id, CancellationToken ct);
    void Add(DataSource source);
    void Remove(DataSource source);
    Task SaveChangesAsync(CancellationToken ct);
}

/// <summary>One unit of data read from a source (a file, a staging table) and how to acknowledge it.</summary>
public sealed record SourcePayload(string Name, RawSheet Sheet, Func<bool, string?, Task> CompleteAsync);

/// <summary>Reads raw rows from an automated data source. Validation and loading stay in the standard import pipeline.</summary>
public interface IDataSourceReader
{
    Task<IReadOnlyList<SourcePayload>> ReadAsync(DataSource source, CancellationToken ct);
    string? InboxRoot { get; }
    IReadOnlyList<string> ConnectionNames { get; }
}

using Broli.SOP.Application.Abstractions;
using Broli.SOP.Domain.Entities;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Infrastructure;

public sealed class SystemClock : IClock
{
    public DateTime UtcNow => DateTime.UtcNow;
    public DateOnly Today => DateOnly.FromDateTime(DateTime.Now);
}

/// <summary>
/// In-process data version. With several API instances behind a load balancer this should move
/// to a shared store (e.g. a SQL row or Redis) — the interface stays the same.
/// </summary>
public sealed class DataVersion : IDataVersion
{
    private long _value = DateTime.UtcNow.Ticks;
    public long Current => Interlocked.Read(ref _value);
    public void Bump() => Interlocked.Increment(ref _value);
}

public sealed class AuditLogger(IAuditRepository repository, ICurrentUser user, IClock clock, ILogger<AuditLogger> logger) : IAuditLogger
{
    public async Task LogAsync(string action, string module, string? objectRef, string? oldValue, string? newValue, CancellationToken ct = default)
    {
        var username = user.IsAuthenticated ? user.Username : objectRef ?? "anonymous";
        repository.Add(new AuditEntry
        {
            TimestampUtc = clock.UtcNow,
            Username = Truncate(username, 80)!,
            Action = Truncate(action, 200)!,
            Module = Truncate(module, 200)!,
            ObjectRef = Truncate(objectRef, 200),
            OldValue = Truncate(oldValue, 4000),
            NewValue = Truncate(newValue, 4000),
        });
        await repository.SaveChangesAsync(ct);
        logger.LogInformation("AUDIT {User} {Action} [{Module}] {Object}", username, action, module, objectRef);
    }

    private static string? Truncate(string? value, int max) => value is null || value.Length <= max ? value : value[..(max - 1)] + "…";
}

/// <summary>Phase 1: notifications are only logged. Swap for e-mail / Teams / in-app delivery later.</summary>
public sealed class LoggingNotificationPublisher(ILogger<LoggingNotificationPublisher> logger) : INotificationPublisher
{
    public Task PublishAsync(SopNotification n, CancellationToken ct = default)
    {
        logger.LogInformation("NOTIFY [{Kind}] {Title}: {Message} ({Link}) → {Audience}", n.Kind, n.Title, n.Message, n.Link, n.Audience ?? "all");
        return Task.CompletedTask;
    }
}

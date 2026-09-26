namespace Broli.SOP.Data.Repositories;

public sealed class ActionRepository(SopDbContext db) : IActionRepository
{
    public async Task<IReadOnlyList<SopAction>> ListAsync(CancellationToken ct) =>
        await db.Actions.AsNoTracking().Include(a => a.RiskItem).OrderBy(a => a.Code).ToListAsync(ct);

    public Task<SopAction?> FindAsync(int id, CancellationToken ct) => db.Actions.Include(a => a.RiskItem).FirstOrDefaultAsync(a => a.Id == id, ct);

    public async Task<string> NextCodeAsync(CancellationToken ct)
    {
        var codes = await db.Actions.Select(a => a.Code).ToListAsync(ct);
        var max = codes.Select(c => int.TryParse(c.AsSpan(c.IndexOf('-') + 1), out var n) ? n : 0).DefaultIfEmpty(0).Max();
        return $"A-{max + 1:0000}";
    }

    public Task<int?> RiskIdAsync(string code, CancellationToken ct) =>
        db.RiskItems.Where(r => r.Code == code).Select(r => (int?)r.Id).FirstOrDefaultAsync(ct);

    public void Add(SopAction action) => db.Actions.Add(action);
    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

public sealed class NotificationRepository(SopDbContext db) : INotificationRepository
{
    public async Task<IReadOnlyList<Recipient>> RecipientsWithPermissionAsync(string permission, CancellationToken ct) =>
        await db.Users.AsNoTracking()
            .Where(u => u.IsActive && u.Roles.Any(ur => ur.Role!.Permissions.Any(p => p.Permission == permission)))
            .Select(u => new Recipient(u.Id, u.Username, u.DisplayName, u.Email))
            .ToListAsync(ct);

    public async Task<Recipient?> FindRecipientAsync(string person, CancellationToken ct)
    {
        // Compared in memory: SQLite's lower() ignores accents ("DÉMO"), and the user list is small.
        var p = person.Trim();
        var users = await db.Users.AsNoTracking().Where(u => u.IsActive)
            .Select(u => new Recipient(u.Id, u.Username, u.DisplayName, u.Email))
            .ToListAsync(ct);
        return users.FirstOrDefault(u => string.Equals(u.Username, p, StringComparison.OrdinalIgnoreCase))
               ?? users.FirstOrDefault(u => string.Equals(u.DisplayName, p, StringComparison.OrdinalIgnoreCase));
    }

    public Task<int?> UserIdAsync(string username, CancellationToken ct)
    {
        var u = username.ToLower();
        return db.Users.Where(x => x.Username.ToLower() == u).Select(x => (int?)x.Id).FirstOrDefaultAsync(ct);
    }

    public void Add(IEnumerable<Notification> notifications) => db.Notifications.AddRange(notifications);

    public async Task<IReadOnlyList<Notification>> ListAsync(int userId, int take, CancellationToken ct) =>
        await db.Notifications.AsNoTracking().Where(n => n.UserId == userId).OrderByDescending(n => n.Id).Take(take).ToListAsync(ct);

    public Task<int> UnreadCountAsync(int userId, CancellationToken ct) =>
        db.Notifications.CountAsync(n => n.UserId == userId && n.ReadAtUtc == null, ct);

    public async Task MarkReadAsync(int userId, long? id, DateTime now, CancellationToken ct) =>
        await db.Notifications.Where(n => n.UserId == userId && n.ReadAtUtc == null && (id == null || n.Id == id))
            .ExecuteUpdateAsync(s => s.SetProperty(n => n.ReadAtUtc, now), ct);

    public async Task<IReadOnlySet<string>> RecentAlertKeysAsync(IReadOnlyCollection<string> keys, DateTime since, CancellationToken ct)
    {
        if (keys.Count == 0) return new HashSet<string>();
        var list = keys.ToList();
        var found = await db.AlertStates.AsNoTracking().Where(a => list.Contains(a.Key) && a.LastRaisedUtc >= since).Select(a => a.Key).ToListAsync(ct);
        return found.ToHashSet();
    }

    public async Task MarkAlertsRaisedAsync(IReadOnlyCollection<string> keys, DateTime now, CancellationToken ct)
    {
        if (keys.Count == 0) return;
        var list = keys.Distinct().ToList();
        var existing = await db.AlertStates.Where(a => list.Contains(a.Key)).ToDictionaryAsync(a => a.Key, ct);
        foreach (var k in list)
        {
            if (existing.TryGetValue(k, out var state)) state.LastRaisedUtc = now;
            else db.AlertStates.Add(new AlertState { Key = k, LastRaisedUtc = now });
        }
        await db.SaveChangesAsync(ct);
    }

    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

public sealed class DataSourceRepository(SopDbContext db) : IDataSourceRepository
{
    public async Task<IReadOnlyList<DataSource>> ListAsync(CancellationToken ct) => await db.DataSources.OrderBy(s => s.Name).ToListAsync(ct);
    public Task<DataSource?> FindAsync(int id, CancellationToken ct) => db.DataSources.FirstOrDefaultAsync(s => s.Id == id, ct);
    public void Add(DataSource source) => db.DataSources.Add(source);
    public void Remove(DataSource source) => db.DataSources.Remove(source);
    public Task SaveChangesAsync(CancellationToken ct) => db.SaveChangesAsync(ct);
}

using Microsoft.Extensions.Logging;

namespace Broli.SOP.Application.Services;

/// <summary>In-app notifications (bell), optionally mirrored by e-mail, plus the notification publisher port.</summary>
public sealed class NotificationService(
    INotificationRepository repository,
    IEmailSender email,
    ISettingsStore settings,
    ICurrentUser user,
    IClock clock,
    ILogger<NotificationService> logger) : INotificationPublisher
{
    public async Task<NotificationFeed> FeedAsync(CancellationToken ct)
    {
        var id = await repository.UserIdAsync(user.Username, ct);
        if (id is null) return new NotificationFeed(0, []);
        var items = await repository.ListAsync(id.Value, 30, ct);
        return new NotificationFeed(await repository.UnreadCountAsync(id.Value, ct),
            items.Select(n => new NotificationDto(n.Id, n.CreatedAtUtc, n.Kind, n.Severity, n.Title, n.Message, n.Link, n.ReadAtUtc.HasValue)).ToList());
    }

    public async Task MarkReadAsync(long? id, CancellationToken ct)
    {
        var uid = await repository.UserIdAsync(user.Username, ct);
        if (uid is not null) await repository.MarkReadAsync(uid.Value, id, clock.UtcNow, ct);
    }

    /// <summary>Notifies every active user holding <paramref name="permission"/>. Returns (notifications, e-mails).</summary>
    public async Task<(int Notifications, int Emails)> NotifyPermissionAsync(string permission, string kind, string severity, string title,
        string message, string? link, CancellationToken ct) =>
        await NotifyAsync(await repository.RecipientsWithPermissionAsync(permission, ct), kind, severity, title, message, link, ct);

    /// <summary>Notifies the user whose username or display name matches <paramref name="person"/>, if there is one.</summary>
    /// <summary>Notifies the user whose username or display name is <paramref name="person"/>; false when there is none.</summary>
    public async Task<bool> NotifyPersonAsync(string person, string kind, string severity, string title, string message, string? link, CancellationToken ct)
    {
        if (await repository.FindRecipientAsync(person, ct) is not { } r) return false;
        await NotifyAsync([r], kind, severity, title, message, link, ct);
        return true;
    }

    private async Task<(int, int)> NotifyAsync(IReadOnlyList<Recipient> recipients, string kind, string severity, string title, string message,
        string? link, CancellationToken ct)
    {
        if (recipients.Count == 0) return (0, 0);
        var now = clock.UtcNow;
        var sendEmail = (await settings.GetAsync(ct)).AlertRules.SendEmail && email.IsConfigured;
        var rows = recipients.Select(r => new Notification
        {
            UserId = r.UserId, CreatedAtUtc = now, Kind = kind, Severity = severity, Title = Cut(title, 200), Message = Cut(message, 2000), Link = link,
        }).ToList();
        repository.Add(rows);
        await repository.SaveChangesAsync(ct);

        var emails = 0;
        if (sendEmail)
        {
            var to = recipients.Select(r => r.Email).OfType<string>().Where(e => e.Contains('@')).Distinct().ToList();
            if (to.Count > 0)
            {
                try
                {
                    await email.SendAsync(new EmailMessage(to, $"[Broli S&OP] {title}", $"{message}\n\n{link}"), ct);
                    emails = to.Count;
                    foreach (var n in rows) n.EmailSent = true;
                    await repository.SaveChangesAsync(ct);
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    // E-mail is best effort: the in-app notification is already stored.
                    logger.LogWarning(ex, "E-mail notification failed: {Title}", title);
                }
            }
        }
        return (rows.Count, emails);
    }

    /// <summary>Generic publisher used by other modules (notifies holders of the audience permission, or everybody with executive.view).</summary>
    public Task PublishAsync(SopNotification n, CancellationToken ct = default) =>
        NotifyPermissionAsync(n.Audience ?? Contracts.Security.Permissions.ExecutiveView, n.Kind, "info", n.Title, n.Message, n.Link, ct);

    private static string Cut(string s, int max) => s.Length <= max ? s : s[..(max - 1)] + "…";
}

/// <summary>
/// Evaluates the alert rules on the current data (stockout risk, ETA delay, coverage below threshold, overdue open PO,
/// overdue actions) and notifies the users concerned with one digest per rule. An object already alerted within
/// <see cref="AlertSettings.RepeatAfterDays"/> days is not repeated.
/// </summary>
public sealed class AlertEngine(
    IAnalyticsEngine engine,
    IActionRepository actions,
    INotificationRepository repository,
    NotificationService notifications,
    ISettingsStore settingsStore,
    IClock clock,
    ILogger<AlertEngine> logger)
{
    public async Task<AlertRunResult> RunAsync(CancellationToken ct)
    {
        var settings = await settingsStore.GetAsync(ct);
        var rules = settings.AlertRules;
        var s = await engine.GetSnapshotAsync(new SopFilter(), ct);
        var since = clock.UtcNow.AddDays(-Math.Max(0, rules.RepeatAfterDays));
        int alerts = 0, sent = 0, emails = 0;

        async Task Digest(bool enabled, string rule, string permission, string severity, string title, string link,
            IEnumerable<(string Key, string Line)> items)
        {
            if (!enabled) return;
            var all = items.GroupBy(i => i.Key).Select(g => g.First()).ToList();
            if (all.Count == 0) return;
            var keys = all.Select(i => $"{rule}:{i.Key}").ToList();
            var recent = await repository.RecentAlertKeysAsync(keys, since, ct);
            var fresh = all.Where(i => !recent.Contains($"{rule}:{i.Key}")).ToList();
            if (fresh.Count == 0) return;
            var body = string.Join("\n", fresh.Take(15).Select(i => "• " + i.Line)) + (fresh.Count > 15 ? $"\n… et {fresh.Count - 15} de plus" : "");
            var (n, e) = await notifications.NotifyPermissionAsync(permission, rule, severity, $"{title} ({fresh.Count})", body, link, ct);
            await repository.MarkAlertsRaisedAsync(fresh.Select(i => $"{rule}:{i.Key}").ToList(), clock.UtcNow, ct);
            alerts += fresh.Count; sent += n; emails += e;
        }

        var pos = s.Positions.Values.ToList();
        await Digest(rules.StockoutRisk, "stockout", Contracts.Security.Permissions.InventoryView, "critical", "Risque de rupture détecté", "inventory?view=critical",
            pos.Where(p => p.Status == CoverageStatus.Critical)
                .Select(p => (p.Product.CArtSap, $"{p.Product.Description} : {p.CoverageMonths:0.0} mois de couverture" + (p.StockoutDate is { } d ? $", rupture le {d:dd/MM}" : ""))));
        await Digest(rules.CoverageBelowThreshold, "coverage", Contracts.Security.Permissions.InventoryView, "high",
            $"Couverture sous {settings.Coverage.RiskBelowMonths:0.#} mois", "inventory?view=risk",
            pos.Where(p => p.Status == CoverageStatus.Risk).Select(p => (p.Product.CArtSap, $"{p.Product.Description} : {p.CoverageMonths:0.0} mois")));
        var open = s.OpenLines.ToList();
        await Digest(rules.EtaDelay, "eta", Contracts.Security.Permissions.SupplyView, "high", "Retard d'ETA", "supply?view=late",
            open.Where(l => l.Assessment.Level >= EtaRiskLevel.SupplyRisk && !(l.Line.Eta is { } e && e < s.Today))
                .Select(l => ($"{l.Line.PoNumber}:{l.Product.CArtSap}:{l.Line.Eta:yyyyMMdd}", $"Commande {l.Line.PoNumber} {l.Product.Description} — {l.Assessment.Reason}")));
        await Digest(rules.OpenPoOverdue, "overdue", Contracts.Security.Permissions.SupplyView, "high", "Commande ouverte en retard", "transit?view=late",
            open.Where(l => l.Line.Eta is { } e && e < s.Today)
                .Select(l => ($"{l.Line.PoNumber}:{l.Product.CArtSap}", $"Commande {l.Line.PoNumber} {l.Product.Description} ({l.Line.SupplierName}) : ETA du {l.Line.Eta:dd/MM} dépassée, non reçue")));

        if (rules.ActionsOverdue)
        {
            var overdue = (await actions.ListAsync(ct))
                .Where(a => a.Status is ActionStatus.Open or ActionStatus.InProgress && a.DueDate is { } d && d < clock.Today).ToList();
            var keys = overdue.Select(a => $"action:{a.Code}").ToList();
            var recent = await repository.RecentAlertKeysAsync(keys, since, ct);
            foreach (var a in overdue.Where(a => !recent.Contains($"action:{a.Code}")))
            {
                await notifications.NotifyPersonAsync(a.Owner, "action", "high", $"L'action {a.Code} est en retard",
                    $"{a.Topic} : {a.Description} — échéance dépassée ({a.DueDate:dd/MM/yyyy})", "actions?view=mine", ct);
                alerts++;
            }
            await repository.MarkAlertsRaisedAsync(overdue.Where(a => !recent.Contains($"action:{a.Code}")).Select(a => $"action:{a.Code}").ToList(), clock.UtcNow, ct);
        }

        logger.LogInformation("Alert run: {Alerts} new alerts, {Notifications} notifications, {Emails} e-mails", alerts, sent, emails);
        return new AlertRunResult(alerts, sent, emails);
    }
}

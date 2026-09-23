namespace Broli.SOP.Application.Services;

/// <summary>The S&amp;OP action plan: actions and decisions with owner, department, due date, priority and status.</summary>
public sealed class ActionService(
    IActionRepository repository,
    NotificationService notifications,
    IAuditLogger audit,
    ICurrentUser user,
    IClock clock)
{
    public async Task<PagedResult<ActionDto>> ListAsync(ActionQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, "DueDate", false);
    }

    public async Task<IReadOnlyList<ActionDto>> ListAllAsync(ActionQuery q, CancellationToken ct)
    {
        var rows = await RowsAsync(q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, "DueDate", false).ToList();
    }

    public async Task<ActionSummary> SummaryAsync(CancellationToken ct)
    {
        var all = (await repository.ListAsync(ct)).Select(ToDto).ToList();
        var today = clock.Today;
        var active = all.Where(a => a.Status is "Open" or "In Progress").ToList();
        return new ActionSummary(
            all.Count(a => a.Status == "Open"), all.Count(a => a.Status == "In Progress"), active.Count(a => a.IsOverdue),
            active.Count(a => a.DueDate is { } d && d >= today && d <= today.AddDays(7)), active.Count(a => a.IsDecision),
            all.Select(a => a.Owner).Distinct().Order().Select(o => new Option(o, o)).ToList(),
            all.Select(a => a.Department).Distinct().Order().ToList());
    }

    private async Task<IEnumerable<ActionDto>> RowsAsync(ActionQuery q, CancellationToken ct)
    {
        IEnumerable<ActionDto> rows = (await repository.ListAsync(ct)).Select(ToDto).ToList();
        if (!string.IsNullOrWhiteSpace(q.Department)) rows = rows.Where(a => a.Department.Equals(q.Department, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(q.Owner)) rows = rows.Where(a => a.Owner.Equals(q.Owner, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(q.Status)) rows = rows.Where(a => Same(a.Status, q.Status));
        if (!string.IsNullOrWhiteSpace(q.Priority)) rows = rows.Where(a => Same(a.Priority, q.Priority));
        if (q.DueBefore is { } due) rows = rows.Where(a => a.DueDate is { } d && d <= due);
        return q.View?.ToLowerInvariant() switch
        {
            "active" => rows.Where(a => a.Status is "Open" or "In Progress"),
            "overdue" => rows.Where(a => a.IsOverdue),
            "decisions" => rows.Where(a => a.IsDecision && a.Status is "Open" or "In Progress"),
            "mine" => rows.Where(a => a.Owner.Equals(user.Username, StringComparison.OrdinalIgnoreCase) || a.CreatedBy.Equals(user.Username, StringComparison.OrdinalIgnoreCase)),
            "done" => rows.Where(a => a.Status is "Done" or "Cancelled"),
            _ => rows,
        };
    }

    private static bool Same(string label, string value) =>
        string.Equals(label.Replace(" ", ""), value.Replace(" ", ""), StringComparison.OrdinalIgnoreCase);

    public async Task<ActionDto> CreateAsync(ActionUpsert request, CancellationToken ct)
    {
        var action = new SopAction
        {
            Code = await repository.NextCodeAsync(ct),
            Date = request.Date ?? clock.Today,
            CreatedAtUtc = clock.UtcNow,
            CreatedBy = user.Username,
        };
        await ApplyAsync(action, request, ct);
        repository.Add(action);
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Created action", "S&OP Actions", action.Code, null, Describe(action), ct);
        await NotifyOwnerAsync(action, "assigned to you", ct);
        return ToDto((await repository.FindAsync(action.Id, ct))!);
    }

    public async Task<ActionDto?> UpdateAsync(int id, ActionUpsert request, CancellationToken ct)
    {
        var action = await repository.FindAsync(id, ct);
        if (action is null) return null;
        var before = Describe(action);
        var previousOwner = action.Owner;
        if (request.Date is { } d) action.Date = d;
        await ApplyAsync(action, request, ct);
        action.UpdatedAtUtc = clock.UtcNow;
        action.UpdatedBy = user.Username;
        await repository.SaveChangesAsync(ct);
        var after = Describe(action);
        if (before != after) await audit.LogAsync("Updated action", "S&OP Actions", action.Code, before, after, ct);
        if (!string.Equals(previousOwner, action.Owner, StringComparison.OrdinalIgnoreCase)) await NotifyOwnerAsync(action, "assigned to you", ct);
        return ToDto((await repository.FindAsync(id, ct))!);
    }

    private async Task ApplyAsync(SopAction a, ActionUpsert r, CancellationToken ct)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(r.Topic)) errors.Add("Topic is required.");
        if (string.IsNullOrWhiteSpace(r.Description)) errors.Add("Description is required.");
        if (string.IsNullOrWhiteSpace(r.Owner)) errors.Add("Owner is required.");
        if (string.IsNullOrWhiteSpace(r.Department)) errors.Add("Department is required.");
        if (!Labels.TryParse<ActionPriority>(r.Priority, out var priority)) errors.Add($"Unknown priority '{r.Priority}'.");
        if (!Labels.TryParse<ActionStatus>(r.Status, out var status)) errors.Add($"Unknown status '{r.Status}'.");
        if (r.Description?.Length > 2000 || r.Comment?.Length > 2000) errors.Add("Description and comment are limited to 2000 characters.");
        int? riskId = null;
        if (!string.IsNullOrWhiteSpace(r.RiskCode))
        {
            riskId = await repository.RiskIdAsync(r.RiskCode.Trim(), ct);
            if (riskId is null) errors.Add($"Unknown risk '{r.RiskCode}'.");
        }
        if (errors.Count > 0) throw new ValidationException(errors);

        a.Topic = r.Topic!.Trim();
        a.Description = r.Description!.Trim();
        a.Owner = r.Owner!.Trim();
        a.Department = r.Department!.Trim();
        a.DueDate = r.DueDate;
        a.Priority = priority;
        a.Status = status;
        a.Comment = string.IsNullOrWhiteSpace(r.Comment) ? null : r.Comment.Trim();
        a.IsDecision = r.IsDecision;
        a.RiskItemId = riskId;
        a.CArtSap = string.IsNullOrWhiteSpace(r.CArtSap) ? null : r.CArtSap.Trim();
    }

    private async Task NotifyOwnerAsync(SopAction a, string what, CancellationToken ct)
    {
        if (a.Status is ActionStatus.Done or ActionStatus.Cancelled) return;
        await notifications.NotifyPersonAsync(a.Owner, "action", a.Priority >= ActionPriority.High ? "high" : "info",
            $"{(a.IsDecision ? "Decision" : "Action")} {a.Code} {what}",
            $"{a.Topic}: {a.Description}" + (a.DueDate is { } d ? $" — due {d:dd/MM/yyyy}" : ""), "actions?view=mine", ct);
    }

    internal ActionDto ToDto(SopAction a) => new(
        a.Id, a.Code, a.Date, a.Topic, a.Description, a.Owner, a.Department, a.DueDate, Labels.Of(a.Priority), Labels.Of(a.Status),
        a.Comment, a.IsDecision, a.RiskItem?.Code, a.CArtSap,
        a.Status is ActionStatus.Open or ActionStatus.InProgress && a.DueDate is { } d && d < clock.Today, a.CreatedBy, a.UpdatedAtUtc);

    private static string Describe(SopAction a) =>
        $"{a.Topic} | {a.Description} | owner {a.Owner} ({a.Department}) | due {a.DueDate:dd/MM/yyyy} | {Labels.Of(a.Priority)} | {Labels.Of(a.Status)}"
        + (a.IsDecision ? " | decision" : "") + (a.Comment is null ? "" : $" | {a.Comment}");

    private static string Search(ActionDto a) => $"{a.Code} {a.Topic} {a.Description} {a.Owner} {a.Department} {a.Comment} {a.RiskCode} {a.CArtSap}";

    private static readonly Dictionary<string, Func<ActionDto, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Code"] = a => a.Code,
        ["Date"] = a => a.Date,
        ["Topic"] = a => a.Topic,
        ["Owner"] = a => a.Owner,
        ["Department"] = a => a.Department,
        ["DueDate"] = a => a.DueDate,
        ["Priority"] = a => a.Priority switch { "Critical" => 4, "High" => 3, "Medium" => 2, _ => 1 },
        ["Status"] = a => a.Status,
    };
}

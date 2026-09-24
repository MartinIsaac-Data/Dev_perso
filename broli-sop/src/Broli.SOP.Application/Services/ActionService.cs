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
        var active = all.Where(a => IsActive(a.Status)).ToList();
        return new ActionSummary(
            all.Count(a => Labels.Is(a.Status, ActionStatus.Open)), all.Count(a => Labels.Is(a.Status, ActionStatus.InProgress)), active.Count(a => a.IsOverdue),
            active.Count(a => a.DueDate is { } d && d >= today && d <= today.AddDays(7)), active.Count(a => a.IsDecision),
            all.Select(a => a.Owner).Distinct().Order().Select(o => new Option(o, o)).ToList(),
            all.Select(a => a.Department).Distinct().Order().ToList());
    }

    private async Task<IEnumerable<ActionDto>> RowsAsync(ActionQuery q, CancellationToken ct)
    {
        IEnumerable<ActionDto> rows = (await repository.ListAsync(ct)).Select(ToDto).ToList();
        if (!string.IsNullOrWhiteSpace(q.Department)) rows = rows.Where(a => a.Department.Equals(q.Department, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(q.Owner)) rows = rows.Where(a => a.Owner.Equals(q.Owner, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(q.Status)) rows = rows.Where(a => Same<ActionStatus>(a.Status, q.Status));
        if (!string.IsNullOrWhiteSpace(q.Priority)) rows = rows.Where(a => Same<ActionPriority>(a.Priority, q.Priority));
        if (q.DueBefore is { } due) rows = rows.Where(a => a.DueDate is { } d && d <= due);
        return q.View?.ToLowerInvariant() switch
        {
            "active" => rows.Where(a => IsActive(a.Status)),
            "overdue" => rows.Where(a => a.IsOverdue),
            "decisions" => rows.Where(a => a.IsDecision && IsActive(a.Status)),
            "mine" => rows.Where(a => a.Owner.Equals(user.Username, StringComparison.OrdinalIgnoreCase) || a.CreatedBy.Equals(user.Username, StringComparison.OrdinalIgnoreCase)),
            "done" => rows.Where(a => Labels.Is(a.Status, ActionStatus.Done) || Labels.Is(a.Status, ActionStatus.Cancelled)),
            _ => rows,
        };
    }

    private static bool IsActive(string status) => Labels.Is(status, ActionStatus.Open) || Labels.Is(status, ActionStatus.InProgress);

    private static bool Same<T>(string label, string value) where T : struct, Enum =>
        Labels.TryParse<T>(value, out var wanted) && Labels.Is(label, wanted);

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
        await audit.LogAsync("Action créée", "Actions S&OP", action.Code, null, Describe(action), ct);
        await NotifyOwnerAsync(action, "vous a été attribuée", ct);
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
        if (before != after) await audit.LogAsync("Action modifiée", "Actions S&OP", action.Code, before, after, ct);
        if (!string.Equals(previousOwner, action.Owner, StringComparison.OrdinalIgnoreCase)) await NotifyOwnerAsync(action, "vous a été attribuée", ct);
        return ToDto((await repository.FindAsync(id, ct))!);
    }

    private async Task ApplyAsync(SopAction a, ActionUpsert r, CancellationToken ct)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(r.Topic)) errors.Add("Le sujet est obligatoire.");
        if (string.IsNullOrWhiteSpace(r.Description)) errors.Add("La description est obligatoire.");
        if (string.IsNullOrWhiteSpace(r.Owner)) errors.Add("Le responsable est obligatoire.");
        if (string.IsNullOrWhiteSpace(r.Department)) errors.Add("Le service est obligatoire.");
        if (!Labels.TryParse<ActionPriority>(r.Priority, out var priority)) errors.Add($"Priorité inconnue : « {r.Priority} ».");
        if (!Labels.TryParse<ActionStatus>(r.Status, out var status)) errors.Add($"Statut inconnu : « {r.Status} ».");
        if (r.Description?.Length > 2000 || r.Comment?.Length > 2000) errors.Add("La description et le commentaire sont limités à 2 000 caractères.");
        int? riskId = null;
        if (!string.IsNullOrWhiteSpace(r.RiskCode))
        {
            riskId = await repository.RiskIdAsync(r.RiskCode.Trim(), ct);
            if (riskId is null) errors.Add($"Risque inconnu : « {r.RiskCode} ».");
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
            $"{(a.IsDecision ? "La décision" : "L'action")} {a.Code} {what}",
            $"{a.Topic} : {a.Description}" + (a.DueDate is { } d ? $" — échéance le {d:dd/MM/yyyy}" : ""), "actions?view=mine", ct);
    }

    internal ActionDto ToDto(SopAction a) => new(
        a.Id, a.Code, a.Date, a.Topic, a.Description, a.Owner, a.Department, a.DueDate, Labels.Of(a.Priority), Labels.Of(a.Status),
        a.Comment, a.IsDecision, a.RiskItem?.Code, a.CArtSap,
        a.Status is ActionStatus.Open or ActionStatus.InProgress && a.DueDate is { } d && d < clock.Today, a.CreatedBy, a.UpdatedAtUtc);

    private static string Describe(SopAction a) =>
        $"{a.Topic} | {a.Description} | responsable {a.Owner} ({a.Department}) | échéance {a.DueDate:dd/MM/yyyy} | {Labels.Of(a.Priority)} | {Labels.Of(a.Status)}"
        + (a.IsDecision ? " | décision" : "") + (a.Comment is null ? "" : $" | {a.Comment}");

    private static string Search(ActionDto a) => $"{a.Code} {a.Topic} {a.Description} {a.Owner} {a.Department} {a.Comment} {a.RiskCode} {a.CArtSap}";

    private static readonly Dictionary<string, Func<ActionDto, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Code"] = a => a.Code,
        ["Date"] = a => a.Date,
        ["Topic"] = a => a.Topic,
        ["Owner"] = a => a.Owner,
        ["Department"] = a => a.Department,
        ["DueDate"] = a => a.DueDate,
        ["Priority"] = a => Labels.Rank<ActionPriority>(a.Priority, 1),
        ["Status"] = a => a.Status,
    };
}

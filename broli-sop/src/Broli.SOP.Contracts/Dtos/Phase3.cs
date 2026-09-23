namespace Broli.SOP.Contracts.Dtos;

// ---------------- S&OP actions ----------------

public record ActionDto(
    int Id,
    string Code,
    DateOnly Date,
    string Topic,
    string Description,
    string Owner,
    string Department,
    DateOnly? DueDate,
    string Priority,
    string Status,
    string? Comment,
    bool IsDecision,
    string? RiskCode,
    string? CArtSap,
    bool IsOverdue,
    string CreatedBy,
    DateTime? UpdatedAtUtc);

public record ActionUpsert(
    DateOnly? Date,
    string Topic,
    string Description,
    string Owner,
    string Department,
    DateOnly? DueDate,
    string Priority,
    string Status,
    string? Comment,
    bool IsDecision,
    string? RiskCode,
    string? CArtSap);

/// <summary>Action list filters (in addition to paging): department, owner, status, priority, due before.</summary>
public class ActionQuery : TableQuery
{
    public string? Department { get; set; }
    public string? Owner { get; set; }
    public string? Status { get; set; }
    public string? Priority { get; set; }
    public DateOnly? DueBefore { get; set; }

    public string ToActionQueryString()
    {
        var parts = new List<string> { ToQueryString() };
        void Add(string k, string? v) { if (!string.IsNullOrWhiteSpace(v)) parts.Add($"{k}={Uri.EscapeDataString(v)}"); }
        Add("department", Department);
        Add("owner", Owner);
        Add("status", Status);
        Add("priority", Priority);
        Add("dueBefore", DueBefore?.ToString("yyyy-MM-dd"));
        return string.Join('&', parts);
    }
}

public record ActionSummary(int Open, int InProgress, int Overdue, int DueThisWeek, int OpenDecisions, IReadOnlyList<Option> Owners, IReadOnlyList<string> Departments);

// ---------------- Meeting view ----------------

public record MeetingKpi(string Label, string Value, string? Sub, string Status, string Link);

public record MeetingSection(string Title, string Question, IReadOnlyList<MeetingKpi> Kpis, IReadOnlyList<MeetingItem> Items, string Link);

public record MeetingItem(string Title, string? Detail, string Severity, string? Link);

public record MeetingView(
    PeriodInfo Period,
    DateTime GeneratedAtUtc,
    MeetingSection Demand,
    MeetingSection Supply,
    MeetingSection Inventory,
    MeetingSection Logistics,
    MeetingSection Risks,
    MeetingSection Opportunities,
    IReadOnlyList<ActionDto> Decisions,
    IReadOnlyList<ActionDto> OverdueActions);

// ---------------- Notifications ----------------

public record NotificationDto(long Id, DateTime CreatedAtUtc, string Kind, string Severity, string Title, string Message, string? Link, bool IsRead);

public record NotificationFeed(int Unread, IReadOnlyList<NotificationDto> Items);

public record AlertRunResult(int Alerts, int Notifications, int Emails);

// ---------------- Data sources & automated refresh ----------------

public record DataSourceDto(
    int Id,
    string Name,
    string Kind,
    string ImportType,
    string Location,
    string? ConnectionName,
    string? DailyAt,
    bool Enabled,
    DateTime? LastRunUtc,
    string? LastStatus,
    string? LastMessage);

public record DataSourceUpsert(string Name, string Kind, string ImportType, string Location, string? ConnectionName, string? DailyAt, bool Enabled);

public record DataSourceRunResult(string Source, string Status, string Message, int Rows, int Errors);

public record RefreshInfo(bool SchedulerEnabled, string? InboxRoot, IReadOnlyList<string> ConnectionNames, IReadOnlyList<DataSourceRunResult> LastRun);

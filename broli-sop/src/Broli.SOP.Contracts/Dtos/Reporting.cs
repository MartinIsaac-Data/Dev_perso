namespace Broli.SOP.Contracts.Dtos;

/// <summary>An S&amp;OP week: <see cref="WeekStart"/> is its Monday (yyyy-MM-dd), used as the key in URLs.</summary>
public record ReportingWeek(string WeekStart, string Label);

/// <summary>One report in one week, with the status the portal derives from the tracker and the dates.</summary>
public record ReportingRow(
    string Code,
    string Department,
    string Name,
    string Owner,
    string Frequency,
    string ExpectedDay,
    string? ExpectedTime,
    DateOnly? ExpectedDate,
    DateOnly? ReceivedDate,
    /// <summary>ReportState name (Received, ReceivedLate, Pending, Late, Missing, NotApplicable).</summary>
    string StateKey,
    string State,
    string? Quality,
    bool RelanceRequired,
    string? Comments,
    int? DaysLate,
    DateTime? LastReminderUtc);

public record ReportingDepartmentStat(
    string Department,
    int Expected,
    int Received,
    int ReceivedLate,
    int Pending,
    int Late,
    int Missing,
    double? ReceptionRatePct);

public record ReportingTrendPoint(string WeekStart, string Label, double? ReceptionRatePct, double? OnTimeRatePct, int LateOrMissing);

/// <summary>Reports expected on a given day of the selected week (the "Unscheduled" day holds daily and unconfirmed reports).</summary>
public record ReportingDay(string Day, DateOnly? Date, IReadOnlyList<ReportingRow> Items);

public record ReportDefinitionDto(
    string Code,
    string Department,
    string Name,
    string Owner,
    string Frequency,
    string ExpectedDay,
    string? ExpectedTime,
    string? MainContent,
    string? CatalogueStatus,
    string? Purpose,
    string? FollowUpNotes,
    bool IsActive,
    /// <summary>Share of the tracked weeks (up to 12) in which the report arrived.</summary>
    double? ReceptionRatePct,
    int WeeksTracked);

public record ReportingDashboard(
    IReadOnlyList<ReportingWeek> Weeks,
    ReportingWeek? Week,
    int Expected,
    int Received,
    int ReceivedLate,
    int Pending,
    int Late,
    int Missing,
    int NotApplicable,
    int QualityIssues,
    int RemindersDue,
    double? ReceptionRatePct,
    double? OnTimeRatePct,
    double? PreviousReceptionRatePct,
    IReadOnlyList<ReportingDepartmentStat> ByDepartment,
    IReadOnlyList<ReportingTrendPoint> Trend,
    IReadOnlyList<ChartPoint> LateByOwner,
    IReadOnlyList<ReportingDay> Calendar,
    IReadOnlyList<ReportingRow> Rows,
    IReadOnlyList<ReportDefinitionDto> Catalogue,
    bool HasDemoData,
    DateTime? LastImportUtc);

public record ReportingImportPreview(
    Guid Id,
    string FileName,
    int Reports,
    int NewReports,
    int UpdatedReports,
    int DeactivatedReports,
    int TrackerRows,
    int EmptyTrackerRows,
    IReadOnlyList<string> Weeks,
    IReadOnlyList<ImportIssue> Issues,
    int ErrorCount,
    int WarningCount,
    bool CanCommit,
    bool WillReplaceDemo);

public record ReportingImportResult(int Reports, int Deactivated, int TrackerRows, IReadOnlyList<string> Weeks, bool ReplacedDemo);

public record ReportingReminderRequest(string Code, string WeekStart);

public record ReportingReminderResult(int Reports, int Notified, IReadOnlyList<string> UnknownOwners);

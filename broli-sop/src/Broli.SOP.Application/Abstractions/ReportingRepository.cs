using Broli.SOP.Application.Reporting;

namespace Broli.SOP.Application.Abstractions;

public record ReportWeekInfo(DateOnly WeekStart, string Label);

public interface IReportingRepository
{
    Task<IReadOnlyList<ReportDefinition>> DefinitionsAsync(CancellationToken ct);
    /// <summary>Weeks present in the tracker, with the label entered in the file.</summary>
    Task<IReadOnlyList<ReportWeekInfo>> WeeksAsync(CancellationToken ct);
    Task<IReadOnlyList<ReportSubmission>> SubmissionsAsync(DateOnly fromWeek, DateOnly toWeek, CancellationToken ct);
    /// <summary>
    /// Replaces the catalogue (reports missing from the file are deactivated, never deleted) and upserts the tracker rows of the
    /// weeks in the file, in one transaction. DEMO reporting rows are removed first.
    /// </summary>
    Task<ReportingImportResult> ImportAsync(IReadOnlyList<ReportDefinitionRow> definitions, IReadOnlyList<ReportSubmissionRow> submissions,
        string fileName, string username, int warnings, CancellationToken ct);
    Task MarkRemindedAsync(int definitionId, DateOnly weekStart, string weekLabel, DateTime utc, CancellationToken ct);
    Task<DateTime?> LastImportAsync(CancellationToken ct);
}

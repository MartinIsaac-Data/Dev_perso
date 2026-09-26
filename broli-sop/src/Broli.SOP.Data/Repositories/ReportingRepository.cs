using Broli.SOP.Application.Reporting;

namespace Broli.SOP.Data.Repositories;

public sealed class ReportingRepository(SopDbContext db, IClock clock) : IReportingRepository
{
    public async Task<IReadOnlyList<ReportDefinition>> DefinitionsAsync(CancellationToken ct) =>
        await db.ReportDefinitions.AsNoTracking().OrderBy(d => d.Id).ToListAsync(ct);

    public async Task<IReadOnlyList<ReportWeekInfo>> WeeksAsync(CancellationToken ct)
    {
        var rows = await db.ReportSubmissions.AsNoTracking().Where(s => s.Report!.IsActive)
            .GroupBy(s => s.WeekStart).Select(g => new { g.Key, Label = g.Min(s => s.WeekLabel) }).ToListAsync(ct);
        return rows.Select(r => new ReportWeekInfo(r.Key, r.Label ?? ReportSchedule.WeekLabel(r.Key))).OrderByDescending(w => w.WeekStart).ToList();
    }

    public async Task<IReadOnlyList<ReportSubmission>> SubmissionsAsync(DateOnly fromWeek, DateOnly toWeek, CancellationToken ct) =>
        await db.ReportSubmissions.AsNoTracking().Where(s => s.WeekStart >= fromWeek && s.WeekStart <= toWeek).ToListAsync(ct);

    public async Task<ReportingImportResult> ImportAsync(IReadOnlyList<ReportDefinitionRow> definitions, IReadOnlyList<ReportSubmissionRow> submissions,
        string fileName, string username, int warnings, CancellationToken ct)
    {
        var strategy = db.Database.CreateExecutionStrategy();
        return await strategy.ExecuteAsync(async () =>
        {
            await using var tx = await db.Database.BeginTransactionAsync(ct);
            var replacedDemo = await db.ReportDefinitions.AnyAsync(d => d.IsDemo, ct);
            if (replacedDemo)
            {
                await db.ReportSubmissions.Where(s => s.IsDemo || s.Report!.IsDemo).ExecuteDeleteAsync(ct);
                await db.ReportDefinitions.Where(d => d.IsDemo).ExecuteDeleteAsync(ct);
            }

            var existing = await db.ReportDefinitions.ToDictionaryAsync(d => d.Code.ToUpper(), ct);
            var codes = definitions.Select(d => d.Code.ToUpperInvariant()).ToHashSet();
            foreach (var row in definitions)
            {
                if (!existing.TryGetValue(row.Code.ToUpperInvariant(), out var d))
                {
                    d = new ReportDefinition { Code = row.Code };
                    db.ReportDefinitions.Add(d);
                    existing[row.Code.ToUpperInvariant()] = d;
                }
                d.Department = row.Department;
                d.Name = row.Name;
                d.Owner = row.Owner;
                d.Frequency = row.Frequency;
                d.ExpectedDay = row.ExpectedDay;
                d.ExpectedTime = row.ExpectedTime;
                d.MainContent = row.MainContent;
                d.CatalogueStatus = row.CatalogueStatus;
                d.Purpose = row.Purpose;
                d.FollowUpNotes = row.FollowUpNotes;
                d.IsActive = true;
            }
            var deactivated = 0;
            foreach (var d in existing.Values.Where(d => d.IsActive && !codes.Contains(d.Code.ToUpperInvariant())))
            {
                d.IsActive = false;
                deactivated++;
            }
            await db.SaveChangesAsync(ct);

            var weeks = submissions.Select(s => s.WeekStart).Distinct().ToList();
            var current = await db.ReportSubmissions.Where(s => weeks.Contains(s.WeekStart))
                .ToDictionaryAsync(s => (s.ReportDefinitionId, s.WeekStart), ct);
            foreach (var row in submissions)
            {
                var definitionId = existing[row.Code.ToUpperInvariant()].Id;
                if (!current.TryGetValue((definitionId, row.WeekStart), out var s))
                {
                    s = new ReportSubmission { ReportDefinitionId = definitionId, WeekStart = row.WeekStart };
                    db.ReportSubmissions.Add(s);
                }
                s.WeekLabel = row.WeekLabel;
                s.ReferenceDate = row.ReferenceDate;
                s.ExpectedDate = row.ExpectedDate;
                s.ReceivedDate = row.ReceivedDate;
                s.Status = row.Status;
                s.Quality = row.Quality;
                s.RelanceRequired = row.RelanceRequired;
                s.Comments = row.Comments;
            }

            db.ImportBatches.Add(new ImportBatch
            {
                Type = ImportType.ReportingCatalogue, FileName = fileName, UploadedBy = username, UploadedAtUtc = clock.UtcNow,
                RowCount = definitions.Count + submissions.Count, InsertedCount = definitions.Count + submissions.Count,
                WarningCount = warnings, Status = ImportStatus.Committed,
            });
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
            db.ChangeTracker.Clear();

            var labels = submissions.GroupBy(s => s.WeekStart).OrderBy(g => g.Key).Select(g => g.First().WeekLabel).ToList();
            return new ReportingImportResult(definitions.Count, deactivated, submissions.Count, labels, replacedDemo);
        });
    }

    public async Task MarkRemindedAsync(int definitionId, DateOnly weekStart, string weekLabel, DateTime utc, CancellationToken ct)
    {
        var s = await db.ReportSubmissions.FirstOrDefaultAsync(x => x.ReportDefinitionId == definitionId && x.WeekStart == weekStart, ct);
        if (s is null)
        {
            var isDemo = await db.ReportDefinitions.Where(d => d.Id == definitionId).Select(d => d.IsDemo).FirstAsync(ct);
            s = new ReportSubmission { ReportDefinitionId = definitionId, WeekStart = weekStart, WeekLabel = weekLabel, IsDemo = isDemo };
            db.ReportSubmissions.Add(s);
        }
        s.LastReminderUtc = utc;
        await db.SaveChangesAsync(ct);
    }

    public Task<DateTime?> LastImportAsync(CancellationToken ct) =>
        db.ImportBatches.Where(b => b.Type == ImportType.ReportingCatalogue && b.Status == ImportStatus.Committed)
            .MaxAsync(b => (DateTime?)b.UploadedAtUtc, ct);
}

using System.Globalization;
using System.Text.RegularExpressions;
using Broli.SOP.Application.Services;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;

namespace Broli.SOP.Application.Reporting;

/// <summary>
/// Weekly follow-up of the reports each department owes the S&amp;OP process: catalogue, tracker and calendar come from one
/// workbook uploaded by an administrator (preview, then commit — nothing invalid is imported).
/// </summary>
public sealed partial class ReportingService(
    IReportingRepository repository,
    IExcelReader reader,
    NotificationService notifications,
    IAuditLogger audit,
    IClock clock,
    IMemoryCache cache,
    ILogger<ReportingService> logger)
{
    public const int TrendWeeks = 12;
    private const string Module = "Suivi des reportings";
    private static readonly TimeSpan StagingDuration = TimeSpan.FromMinutes(30);
    private static readonly CultureInfo Fr = CultureInfo.GetCultureInfo("fr-FR");

    private sealed record Staged(Guid Id, string FileName, string Username, ReportingWorkbookOutcome Outcome);

    // ---------------------------------------------------------------- dashboard

    public async Task<ReportingDashboard> GetDashboardAsync(string? week, CancellationToken ct)
    {
        var today = clock.Today;
        var definitions = await repository.DefinitionsAsync(ct);
        var active = definitions.Where(d => d.IsActive).ToList();
        var weeks = await WeeksAsync(active.Count > 0, today, ct);
        var lastImport = await repository.LastImportAsync(ct);
        var hasDemo = definitions.Any(d => d.IsDemo);

        if (weeks.Count == 0)
            return new ReportingDashboard([], null, 0, 0, 0, 0, 0, 0, 0, 0, 0, null, null, null, [], [], [], [], [], Catalogue(definitions, [], []),
                hasDemo, lastImport);

        var selected = weeks.FirstOrDefault(w => w.WeekStart == ParseWeekKey(week)) ?? await DefaultWeekAsync(weeks, today, ct);
        var trendWeeks = weeks.Where(w => w.WeekStart <= selected.WeekStart).OrderByDescending(w => w.WeekStart).Take(TrendWeeks)
            .OrderBy(w => w.WeekStart).ToList();
        var submissions = await repository.SubmissionsAsync(trendWeeks[0].WeekStart, selected.WeekStart, ct);
        var byWeek = submissions.ToLookup(s => s.WeekStart);

        var rowsByWeek = trendWeeks.ToDictionary(w => w.WeekStart, w => Rows(active, byWeek[w.WeekStart], w.WeekStart, today));
        var rows = rowsByWeek[selected.WeekStart];
        var counts = Count(rows);
        var trend = trendWeeks.Select(w =>
        {
            var c = Count(rowsByWeek[w.WeekStart]);
            return new ReportingTrendPoint(Key(w.WeekStart), w.Label, c.ReceptionRate, c.OnTimeRate, c.Late + c.Missing);
        }).ToList();
        var previous = trend.Count > 1 ? trend[^2].ReceptionRatePct : null;

        var byDepartment = rows.GroupBy(r => r.Department)
            .Select(g => { var c = Count(g.ToList()); return new ReportingDepartmentStat(g.Key, c.Expected, c.Received, c.ReceivedLate, c.Pending, c.Late, c.Missing, c.ReceptionRate); })
            .ToList();

        var lateByOwner = rowsByWeek.Values.SelectMany(r => r)
            .Where(r => r.StateKey is nameof(ReportState.Late) or nameof(ReportState.Missing) or nameof(ReportState.ReceivedLate))
            .GroupBy(r => r.Owner).Select(g => new ChartPoint(g.Key, g.Count(), g.Key))
            .OrderByDescending(p => p.Value).ThenBy(p => p.Label).Take(8).ToList();

        return new ReportingDashboard(weeks.Select(w => new ReportingWeek(Key(w.WeekStart), Label(w))).ToList(),
            new ReportingWeek(Key(selected.WeekStart), Label(selected)),
            counts.Expected, counts.Received, counts.ReceivedLate, counts.Pending, counts.Late, counts.Missing, counts.NotApplicable,
            rows.Count(r => r.Quality == Labels.Of(ReportQuality.Issue)),
            rows.Count(NeedsReminder),
            counts.ReceptionRate, counts.OnTimeRate, previous,
            byDepartment, trend, lateByOwner, Calendar(rows, selected.WeekStart),
            rows.OrderBy(r => Severity(r.StateKey)).ThenBy(r => r.ExpectedDate ?? DateOnly.MaxValue).ThenBy(r => r.Code).ToList(),
            Catalogue(definitions, rowsByWeek.Values.ToList(), active),
            hasDemo, lastImport);
    }

    /// <summary>The rows of one week, for the Excel / CSV export.</summary>
    public async Task<(ReportingWeek? Week, IReadOnlyList<ReportingRow> Rows)> GetWeekRowsAsync(string? week, CancellationToken ct)
    {
        var d = await GetDashboardAsync(week, ct);
        return (d.Week, d.Rows);
    }

    private static bool NeedsReminder(ReportingRow r) =>
        r.StateKey is nameof(ReportState.Late) or nameof(ReportState.Missing)
        || r.RelanceRequired && r.StateKey is not (nameof(ReportState.Received) or nameof(ReportState.ReceivedLate) or nameof(ReportState.NotApplicable));

    private static int Severity(string state) => state switch
    {
        nameof(ReportState.Missing) => 0,
        nameof(ReportState.Late) => 1,
        nameof(ReportState.Pending) => 2,
        nameof(ReportState.ReceivedLate) => 3,
        nameof(ReportState.Received) => 4,
        _ => 5,
    };

    private async Task<List<ReportWeekInfo>> WeeksAsync(bool hasReports, DateOnly today, CancellationToken ct)
    {
        var weeks = (await repository.WeeksAsync(ct)).ToList();
        var current = ReportSchedule.WeekStart(today);
        if (hasReports && weeks.All(w => w.WeekStart != current)) weeks.Add(new ReportWeekInfo(current, ReportSchedule.WeekLabel(current)));
        return hasReports ? weeks.OrderByDescending(w => w.WeekStart).ToList() : [];
    }

    /// <summary>The most recent week filled in the tracker (up to the current one), else the current week.</summary>
    private async Task<ReportWeekInfo> DefaultWeekAsync(List<ReportWeekInfo> weeks, DateOnly today, CancellationToken ct)
    {
        var current = ReportSchedule.WeekStart(today);
        var tracked = (await repository.WeeksAsync(ct)).Select(w => w.WeekStart).Where(w => w <= current).DefaultIfEmpty(current).Max();
        return weeks.First(w => w.WeekStart == tracked);
    }

    private static List<ReportingRow> Rows(IReadOnlyList<ReportDefinition> active, IEnumerable<ReportSubmission> submissions, DateOnly week, DateOnly today)
    {
        var byDefinition = submissions.ToDictionary(s => s.ReportDefinitionId);
        return active.Select(d =>
        {
            byDefinition.TryGetValue(d.Id, out var s);
            var due = s?.ExpectedDate ?? ReportSchedule.Due(d.ExpectedDay, week);
            var state = ReportSchedule.State(s?.Status, due, s?.ReceivedDate, week, today);
            return new ReportingRow(d.Code, d.Department, d.Name, d.Owner, ReportSchedule.FrequencyLabel(d.Frequency), ReportSchedule.DayLabel(d.ExpectedDay),
                d.ExpectedTime, due, s?.ReceivedDate,
                state.ToString(), Labels.Of(state), s?.Quality is { } q ? Labels.Of(q) : null, s?.RelanceRequired ?? false, s?.Comments,
                ReportSchedule.DaysLate(state, due, s?.ReceivedDate, week, today), s?.LastReminderUtc);
        }).ToList();
    }

    private sealed record Counts(int Expected, int Received, int ReceivedLate, int Pending, int Late, int Missing, int NotApplicable)
    {
        private int Due => Received + ReceivedLate + Late + Missing;
        /// <summary>Share of the reports already due that arrived; reports not yet due are left out.</summary>
        public double? ReceptionRate => Mapping.R(KpiMath.Pct(Received + ReceivedLate, Due));
        public double? OnTimeRate => Mapping.R(KpiMath.Pct(Received, Due));
    }

    private static Counts Count(IReadOnlyCollection<ReportingRow> rows)
    {
        int N(ReportState s) => rows.Count(r => r.StateKey == s.ToString());
        var na = N(ReportState.NotApplicable);
        return new Counts(rows.Count - na, N(ReportState.Received), N(ReportState.ReceivedLate), N(ReportState.Pending), N(ReportState.Late),
            N(ReportState.Missing), na);
    }

    private static IReadOnlyList<ReportingDay> Calendar(IReadOnlyList<ReportingRow> rows, DateOnly week)
    {
        var days = new List<ReportingDay>();
        for (var i = 0; i < 7; i++)
        {
            var date = week.AddDays(i);
            var items = rows.Where(r => ReportSchedule.Parse(r.ExpectedDay) is { Kind: ScheduleKind.Weekly } s && s.Day == date.DayOfWeek)
                .OrderBy(r => r.ExpectedTime ?? "99").ThenBy(r => r.Code).ToList();
            if (items.Count > 0) days.Add(new ReportingDay(ReportSchedule.DayName(date.DayOfWeek), date, items));
        }
        var daily = rows.Where(r => ReportSchedule.Parse(r.ExpectedDay).Kind == ScheduleKind.Daily).OrderBy(r => r.Code).ToList();
        if (daily.Count > 0) days.Add(new ReportingDay("Tous les jours", null, daily));
        var other = rows.Where(r => ReportSchedule.Parse(r.ExpectedDay).Kind is not (ScheduleKind.Weekly or ScheduleKind.Daily)).OrderBy(r => r.Code).ToList();
        if (other.Count > 0) days.Add(new ReportingDay("Jour à confirmer", null, other));
        return days;
    }

    private static IReadOnlyList<ReportDefinitionDto> Catalogue(IReadOnlyList<ReportDefinition> definitions, IReadOnlyList<List<ReportingRow>> weeks,
        IReadOnlyList<ReportDefinition> active)
    {
        var history = weeks.SelectMany(w => w)
            .Where(r => r.StateKey is not (nameof(ReportState.Pending) or nameof(ReportState.NotApplicable)))
            .GroupBy(r => r.Code)
            .ToDictionary(g => g.Key, g => (Weeks: g.Count(), Received: g.Count(r => r.StateKey is nameof(ReportState.Received) or nameof(ReportState.ReceivedLate))));
        return definitions.OrderBy(d => !d.IsActive).ThenBy(d => d.Id).Select(d =>
        {
            var h = history.GetValueOrDefault(d.Code);
            return new ReportDefinitionDto(d.Code, d.Department, d.Name, d.Owner, ReportSchedule.FrequencyLabel(d.Frequency), ReportSchedule.DayLabel(d.ExpectedDay),
                d.ExpectedTime, d.MainContent, ReportSchedule.CatalogueStatusLabel(d.CatalogueStatus), d.Purpose, d.FollowUpNotes, d.IsActive, Mapping.R(KpiMath.Pct(h.Received, h.Weeks)), h.Weeks);
        }).ToList();
    }

    private static string Key(DateOnly week) => week.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Label(ReportWeekInfo w) => $"{w.Label} · {w.WeekStart.ToString("dd/MM", Fr)} – {w.WeekStart.AddDays(6).ToString("dd/MM", Fr)}";

    private static DateOnly? ParseWeekKey(string? week) =>
        DateOnly.TryParseExact(week, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var d) ? ReportSchedule.WeekStart(d) : null;

    // ---------------------------------------------------------------- import

    public async Task<ReportingImportPreview> PreviewAsync(string fileName, Stream content, string username, CancellationToken ct)
    {
        IReadOnlyList<NamedSheet> sheets;
        try
        {
            sheets = reader.ReadAll(content);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogWarning(ex, "Unreadable reporting workbook {File}", fileName);
            throw new ValidationException([$"Le fichier n'a pas pu être lu comme un classeur Excel (.xlsx) : {ex.Message}"]);
        }

        var outcome = ReportingWorkbook.Read(sheets, clock.Today);
        var existing = await repository.DefinitionsAsync(ct);
        var real = existing.Where(d => !d.IsDemo).ToList();
        var codes = outcome.Definitions.Select(d => d.Code).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var known = real.Select(d => d.Code).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var deactivated = real.Count(d => d.IsActive && !codes.Contains(d.Code));
        var issues = outcome.Issues.ToList();
        if (deactivated > 0)
            issues.Add(new ImportIssue(0, null,
                $"{deactivated} reporting(s) absent(s) du fichier ne seront plus attendus ; leur historique est conservé.", "Warning"));

        var staged = new Staged(Guid.NewGuid(), fileName, username, outcome with { Issues = issues });
        cache.Set(StageKey(staged.Id), staged, new MemoryCacheEntryOptions { AbsoluteExpirationRelativeToNow = StagingDuration, Size = 1 });
        logger.LogInformation("Reporting workbook preview {File}: {Reports} reports, {Rows} tracker rows, {Errors} errors",
            fileName, outcome.Definitions.Count, outcome.Submissions.Count, staged.Outcome.ErrorCount);

        return new ReportingImportPreview(staged.Id, fileName, outcome.Definitions.Count, codes.Count(c => !known.Contains(c)),
            codes.Count(known.Contains), deactivated, outcome.Submissions.Count, outcome.EmptyTrackerRows,
            outcome.Submissions.Select(s => s.WeekStart).Distinct().OrderBy(w => w).Select(w => outcome.Submissions.First(s => s.WeekStart == w).WeekLabel).ToList(),
            issues.OrderByDescending(i => i.Severity == "Error").ThenBy(i => i.Column).ThenBy(i => i.Row).ToList(),
            staged.Outcome.ErrorCount, staged.Outcome.WarningCount, staged.Outcome.CanCommit, existing.Any(d => d.IsDemo));
    }

    public async Task<ReportingImportResult> CommitAsync(Guid id, string username, CancellationToken ct)
    {
        if (!cache.TryGetValue(StageKey(id), out Staged? staged) || staged is null)
            throw new ValidationException(["Cet aperçu a expiré. Chargez à nouveau le fichier."]);
        if (!string.Equals(staged.Username, username, StringComparison.OrdinalIgnoreCase))
            throw new ValidationException(["Seul l'utilisateur qui a chargé le fichier peut l'importer."]);
        if (!staged.Outcome.CanCommit)
            throw new ValidationException([$"Le fichier contient {staged.Outcome.ErrorCount} erreur(s). Corrigez-les et chargez-le à nouveau — rien n'a été importé."]);

        var result = await repository.ImportAsync(staged.Outcome.Definitions, staged.Outcome.Submissions, staged.FileName, username,
            staged.Outcome.WarningCount, ct);
        cache.Remove(StageKey(id));
        await audit.LogAsync("Fichier de suivi importé", Module, staged.FileName, null,
            $"{result.Reports} reportings, {result.TrackerRows} lignes de suivi ({string.Join(", ", result.Weeks)})"
            + (result.Deactivated > 0 ? $", {result.Deactivated} désactivé(s)" : "") + (result.ReplacedDemo ? ", données de DÉMO remplacées" : ""), ct);
        return result;
    }

    private static string StageKey(Guid id) => $"reporting-import:{id}";

    // ---------------------------------------------------------------- reminders

    public async Task<ReportingReminderResult> RemindAsync(ReportingReminderRequest request, CancellationToken ct)
    {
        var dashboard = await GetDashboardAsync(request.WeekStart, ct);
        if (dashboard.Week is null || dashboard.Week.WeekStart != request.WeekStart)
            throw new ValidationException([$"Semaine inconnue : « {request.WeekStart} »."]);
        var targets = string.IsNullOrWhiteSpace(request.Code)
            ? dashboard.Rows.Where(NeedsReminder).ToList()
            : dashboard.Rows.Where(r => string.Equals(r.Code, request.Code, StringComparison.OrdinalIgnoreCase)).ToList();
        if (targets.Count == 0)
            throw new ValidationException([string.IsNullOrWhiteSpace(request.Code) ? "Aucun reporting à relancer cette semaine." : $"Reporting inconnu : « {request.Code} »."]);

        var definitions = (await repository.DefinitionsAsync(ct)).ToDictionary(d => d.Code, StringComparer.OrdinalIgnoreCase);
        var week = ParseWeekKey(request.WeekStart)!.Value;
        var notified = 0;
        var unknown = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in targets)
        {
            var due = row.ExpectedDate is { } d ? $" (attendu le {d.ToString("dd/MM", Fr)})" : "";
            var sent = 0;
            foreach (var person in Owners(row.Owner))
            {
                if (await notifications.NotifyPersonAsync(person, "reporting", "high", $"Relance : {row.Code} — {row.Name}",
                        $"Merci d'envoyer le reporting « {row.Name} » pour la semaine {dashboard.Week.Label}{due}.", $"reporting?week={request.WeekStart}", ct))
                    sent++;
                else unknown.Add(person);
            }
            notified += sent;
            await repository.MarkRemindedAsync(definitions[row.Code].Id, week, dashboard.Weeks.First(w => w.WeekStart == request.WeekStart).Label.Split(" · ")[0],
                clock.UtcNow, ct);
            await audit.LogAsync("Relance envoyée", Module, $"{row.Code} {dashboard.Week.Label}", null,
                $"{row.Owner} — {sent} destinataire(s) notifié(s)", ct);
        }
        return new ReportingReminderResult(targets.Count, notified, unknown.ToList());
    }

    /// <summary>"Joel Yogo / Guillaume Tamba" → two people.</summary>
    public static IEnumerable<string> Owners(string owner) =>
        OwnerSeparator().Split(owner).Select(o => o.Trim()).Where(o => o.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase);

    [GeneratedRegex(@"\s*(?:/|,|;|&|\bet\b|\band\b)\s*", RegexOptions.IgnoreCase)]
    private static partial Regex OwnerSeparator();
}

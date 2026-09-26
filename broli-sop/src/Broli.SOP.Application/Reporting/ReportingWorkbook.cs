using System.Globalization;
using System.Text.RegularExpressions;
using Broli.SOP.Application.Import;

namespace Broli.SOP.Application.Reporting;

public record ReportDefinitionRow(
    int ExcelRow, string Code, string Department, string Name, string Owner, string Frequency, string ExpectedDay,
    string? ExpectedTime, string? MainContent, string? CatalogueStatus, string? Purpose, string? FollowUpNotes);

public record ReportSubmissionRow(
    int ExcelRow, string Code, DateOnly WeekStart, string WeekLabel, DateOnly? ReferenceDate, DateOnly? ExpectedDate, DateOnly? ReceivedDate,
    ReportStatus? Status, ReportQuality? Quality, bool RelanceRequired, string? Comments);

public record ReportingWorkbookOutcome(
    IReadOnlyList<ReportDefinitionRow> Definitions,
    IReadOnlyList<ReportSubmissionRow> Submissions,
    int EmptyTrackerRows,
    IReadOnlyList<ImportIssue> Issues)
{
    public int ErrorCount => Issues.Count(i => i.Severity == "Error");
    public int WarningCount => Issues.Count(i => i.Severity == "Warning");
    public bool CanCommit => ErrorCount == 0 && Definitions.Count > 0;
}

/// <summary>
/// Reads the S&amp;OP reporting workbook: 01_REPORTING_CATALOGUE (required), 02_REPORTING_TRACKER and 03_REPORTING_CALENDAR
/// (optional). Sheets and columns are found by name, French or English, accents and case ignored. Any error blocks the import.
/// </summary>
public static partial class ReportingWorkbook
{
    private const int MaxIssues = 500;

    private sealed record Col(string Name, bool Required, params string[] Aliases);

    private static readonly Col[] CatalogueColumns =
    [
        new("Reporting ID", true, "id", "code", "reporting", "id reporting", "code reporting"),
        new("Department", true, "departement", "service", "direction"),
        new("Reporting Name", true, "name", "nom", "nom du reporting", "reporting", "intitule"),
        new("Owner / Preparer", true, "owner", "preparer", "responsable", "proprietaire"),
        new("Frequency", false, "frequence", "periodicite"),
        new("Expected Day", false, "jour", "jour attendu", "day"),
        new("Main Content", false, "content", "contenu", "contenu principal"),
        new("Status / Current State", false, "status", "statut", "current state", "etat"),
    ];

    private static readonly Col[] TrackerColumns =
    [
        new("S&OP Week", false, "week", "semaine", "semaine s&op", "sop week"),
        new("Reference Date", false, "date de reference", "date reference"),
        new("Reporting ID", true, "id", "code", "id reporting", "code reporting"),
        new("Expected Date", false, "date attendue", "echeance"),
        new("Received Date", false, "date de reception", "date recue", "date reception", "received"),
        new("Status", false, "statut"),
        new("Data Quality", false, "quality", "qualite", "qualite des donnees"),
        new("Relance Required", false, "relance", "reminder", "relance necessaire"),
        new("Comments", false, "comment", "commentaire", "commentaires"),
    ];

    private static readonly Col[] CalendarColumns =
    [
        new("Day", false, "jour"),
        new("Reporting ID", true, "id", "code", "id reporting", "code reporting"),
        new("Expected Time", false, "heure", "heure attendue", "time"),
        new("Purpose", false, "objectif", "finalite", "usage"),
        new("Follow-up Notes", false, "notes", "notes de suivi", "suivi", "follow up notes"),
    ];

    private static readonly string[] TrackerInputs = ["S&OP Week", "Reference Date", "Expected Date", "Received Date", "Status", "Data Quality", "Relance Required", "Comments"];

    public static ReportingWorkbookOutcome Read(IReadOnlyList<NamedSheet> sheets, DateOnly today)
    {
        var issues = new List<ImportIssue>();
        var catalogue = Find(sheets, "catalogue", "catalog", "referentiel");
        var tracker = Find(sheets, "tracker", "suivi");
        var calendar = Find(sheets, "calendar", "calendrier", "planning");

        if (catalogue is null)
        {
            issues.Add(new ImportIssue(0, null,
                $"Onglet catalogue introuvable (attendu : 01_REPORTING_CATALOGUE). Onglets du fichier : {string.Join(", ", sheets.Select(s => s.Name))}.", "Error"));
            return new ReportingWorkbookOutcome([], [], 0, issues);
        }

        var definitions = ReadCatalogue(catalogue, issues);
        var byCode = definitions.ToDictionary(d => d.Code, StringComparer.OrdinalIgnoreCase);
        if (calendar is not null) definitions = MergeCalendar(calendar, definitions, byCode, issues);

        var empty = 0;
        var submissions = tracker is null ? [] : ReadTracker(tracker, byCode, today, issues, out empty);

        if (issues.Count > MaxIssues)
        {
            issues.RemoveRange(MaxIssues, issues.Count - MaxIssues);
            issues.Add(new ImportIssue(0, null, $"Validation arrêtée après {MaxIssues} anomalies. Corrigez d'abord celles-ci.", "Error"));
        }
        return new ReportingWorkbookOutcome(definitions, submissions, empty, issues);
    }

    private static NamedSheet? Find(IReadOnlyList<NamedSheet> sheets, params string[] keys) =>
        sheets.FirstOrDefault(s => keys.Any(k => CellParser.Normalize(s.Name).Contains(k)));

    private static Dictionary<string, int>? MapColumns(NamedSheet sheet, Col[] spec, List<ImportIssue> issues)
    {
        var headers = sheet.Sheet.Headers.Select(CellParser.Normalize).ToList();
        var map = new Dictionary<string, int>();
        var ok = true;
        foreach (var col in spec)
        {
            var names = new[] { col.Name }.Concat(col.Aliases).Select(CellParser.Normalize).ToHashSet();
            var i = headers.FindIndex(h => names.Contains(h));
            if (i >= 0 && !map.ContainsValue(i)) map[col.Name] = i;
            else if (col.Required)
            {
                issues.Add(new ImportIssue(0, $"{sheet.Name} › {col.Name}", $"Colonne obligatoire manquante : « {col.Name} ».", "Error"));
                ok = false;
            }
        }
        return ok ? map : null;
    }

    private static object? Cell(RawRow row, Dictionary<string, int> map, string col) =>
        map.TryGetValue(col, out var i) && i < row.Cells.Count ? row.Cells[i] : null;

    private static string? Text(RawRow row, Dictionary<string, int> map, string col) => CellParser.Text(Cell(row, map, col));

    private static List<ReportDefinitionRow> ReadCatalogue(NamedSheet sheet, List<ImportIssue> issues)
    {
        var result = new List<ReportDefinitionRow>();
        var map = MapColumns(sheet, CatalogueColumns, issues);
        if (map is null) return result;
        var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        foreach (var row in sheet.Sheet.Rows)
        {
            void Error(string col, string message) => issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › {col}", message, "Error"));
            var code = Text(row, map, "Reporting ID");
            var department = Text(row, map, "Department");
            var name = Text(row, map, "Reporting Name");
            var owner = Text(row, map, "Owner / Preparer");
            var errors = issues.Count;
            if (code is null) Error("Reporting ID", "Identifiant du reporting manquant.");
            if (department is null) Error("Department", "Service manquant.");
            if (name is null) Error("Reporting Name", "Nom du reporting manquant.");
            if (owner is null) Error("Owner / Preparer", "Responsable manquant.");
            if (code is { Length: > 40 }) Error("Reporting ID", "Identifiant trop long (40 caractères maximum).");
            foreach (var (col, value) in new[] { ("Department", department), ("Reporting Name", name), ("Owner / Preparer", owner) })
                if (value is { Length: > 200 }) Error(col, "Valeur trop longue (200 caractères maximum).");
            if (code is not null && seen.TryGetValue(code, out var first)) Error("Reporting ID", $"« {code} » est déjà utilisé à la ligne {first}.");
            if (issues.Count > errors) continue;

            seen[code!] = row.ExcelRow;
            var day = Text(row, map, "Expected Day") ?? "";
            var schedule = ReportSchedule.Parse(day);
            if (day.Length == 0)
                issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › Expected Day", $"{code} : jour attendu non renseigné, l'échéance ne pourra pas être calculée.", "Warning"));
            else if (schedule.Kind == ScheduleKind.Unknown)
                issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › Expected Day",
                    $"{code} : jour « {day} » non reconnu (attendu : lundi… dimanche, Every day, To confirm). L'échéance ne pourra pas être calculée.", "Warning"));

            result.Add(new ReportDefinitionRow(row.ExcelRow, code!, department!, name!, owner!, Text(row, map, "Frequency") ?? "", day,
                null, Limit(Text(row, map, "Main Content"), 1000), Limit(Text(row, map, "Status / Current State"), 200), null, null));
        }
        if (result.Count == 0 && issues.All(i => i.Severity != "Error"))
            issues.Add(new ImportIssue(0, sheet.Name, "Le catalogue ne contient aucun reporting.", "Error"));
        return result;
    }

    private static List<ReportDefinitionRow> MergeCalendar(NamedSheet sheet, List<ReportDefinitionRow> definitions,
        Dictionary<string, ReportDefinitionRow> byCode, List<ImportIssue> issues)
    {
        var map = MapColumns(sheet, CalendarColumns, issues);
        if (map is null) return definitions;
        var merged = definitions.ToDictionary(d => d.Code, StringComparer.OrdinalIgnoreCase);
        foreach (var row in sheet.Sheet.Rows)
        {
            var code = Text(row, map, "Reporting ID");
            if (code is null) continue;
            if (!byCode.TryGetValue(code, out var def))
            {
                issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › Reporting ID", $"« {code} » n'est pas dans le catalogue : ligne ignorée.", "Warning"));
                continue;
            }
            var day = Text(row, map, "Day");
            if (day is not null && ReportSchedule.Parse(day) is var cal && ReportSchedule.Parse(def.ExpectedDay) is var cat
                && cal.Kind == ScheduleKind.Weekly && cat.Kind == ScheduleKind.Weekly && cal.Day != cat.Day)
                issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › Day",
                    $"{code} : le calendrier indique « {day} », le catalogue « {def.ExpectedDay} ». Le catalogue fait foi.", "Warning"));

            merged[def.Code] = merged[def.Code] with
            {
                ExpectedTime = Limit(TimeText(Cell(row, map, "Expected Time")), 40),
                Purpose = Limit(Text(row, map, "Purpose"), 200),
                FollowUpNotes = Limit(Text(row, map, "Follow-up Notes"), 1000),
            };
        }
        return definitions.Select(d => merged[d.Code]).ToList();
    }

    private static List<ReportSubmissionRow> ReadTracker(NamedSheet sheet, Dictionary<string, ReportDefinitionRow> byCode, DateOnly today,
        List<ImportIssue> issues, out int emptyRows)
    {
        emptyRows = 0;
        var result = new List<ReportSubmissionRow>();
        var map = MapColumns(sheet, TrackerColumns, issues);
        if (map is null) return result;
        var seen = new Dictionary<(string, DateOnly), int>();

        foreach (var row in sheet.Sheet.Rows)
        {
            if (TrackerInputs.All(c => CellParser.IsBlank(Cell(row, map, c))))
            {
                emptyRows++;
                continue;
            }
            var errors = issues.Count;
            void Error(string col, string message) => issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › {col}", message, "Error"));
            void Warn(string col, string message) => issues.Add(new ImportIssue(row.ExcelRow, $"{sheet.Name} › {col}", message, "Warning"));

            DateOnly? Date(string col)
            {
                var raw = Cell(row, map, col);
                if (CellParser.IsBlank(raw)) return null;
                if (CellParser.TryDate(raw, out var d)) return d;
                Error(col, $"Date invalide : « {CellParser.Text(raw)} ». Utilisez jj/mm/aaaa.");
                return null;
            }

            var code = Text(row, map, "Reporting ID");
            if (code is null) Error("Reporting ID", "Identifiant du reporting manquant.");
            else if (!byCode.ContainsKey(code)) Error("Reporting ID", $"« {code} » n'est pas dans le catalogue.");

            var reference = Date("Reference Date");
            var expected = Date("Expected Date");
            var received = Date("Received Date");
            var weekText = WeekText(Cell(row, map, "S&OP Week"));
            DateOnly? weekStart = reference is { } r ? ReportSchedule.WeekStart(r) : ParseWeek(weekText);
            if (weekStart is null)
                Error(weekText is null ? "Reference Date" : "S&OP Week", weekText is null
                    ? "Renseignez la date de référence (ou la semaine S&OP avec l'année, ex. S39 2026)."
                    : $"Semaine « {weekText} » non reconnue : renseignez la date de référence ou une semaine avec l'année (ex. S39 2026).");

            ReportStatus? status = null;
            if (Text(row, map, "Status") is { } st)
            {
                if (ParseStatus(st) is { } s) status = s;
                else Error("Status", $"Statut inconnu : « {st} ». Valeurs attendues : Pending, Received, Late, Missing, Not Applicable (ou en français).");
            }
            ReportQuality? quality = null;
            if (Text(row, map, "Data Quality") is { } q)
            {
                if (Labels.TryParse<ReportQuality>(q, out var qq)) quality = qq;
                else Error("Data Quality", $"Qualité inconnue : « {q} ». Valeurs attendues : OK, Issue, Pending.");
            }
            var relance = false;
            var relanceRaw = Cell(row, map, "Relance Required");
            if (!CellParser.IsBlank(relanceRaw))
            {
                if (ParseYesNo(relanceRaw) is { } y) relance = y;
                else Error("Relance Required", $"Valeur « {CellParser.Text(relanceRaw)} » non reconnue. Utilisez Yes/No (ou Oui/Non).");
            }

            if (received is not null && status == ReportStatus.Missing)
                Error("Status", "Statut « Missing » alors qu'une date de réception est saisie.");
            if (received is { } rd && rd > today.AddDays(1))
                Warn("Received Date", $"Date de réception dans le futur ({rd:dd/MM/yyyy}).");
            if (status == ReportStatus.Received && received is null)
                Warn("Received Date", "Statut « Received » sans date de réception : le reporting est compté comme reçu à l'heure.");

            if (issues.Count > errors && issues.Skip(errors).Any(i => i.Severity == "Error")) continue;

            var key = (code!.ToUpperInvariant(), weekStart!.Value);
            if (seen.TryGetValue(key, out var first))
            {
                Error("Reporting ID", $"{code} apparaît deux fois pour la même semaine (voir ligne {first}).");
                continue;
            }
            seen[key] = row.ExcelRow;
            var label = weekText is not null && weekText.Length <= 40 ? weekText : ReportSchedule.WeekLabel(weekStart.Value);
            result.Add(new ReportSubmissionRow(row.ExcelRow, byCode[code].Code, weekStart.Value, label, reference, expected, received,
                status, quality, relance, Limit(Text(row, map, "Comments"), 1000)));
        }
        return result;
    }

    private static string? Limit(string? s, int max) => s is null ? null : s.Length <= max ? s : s[..max];

    private static string? WeekText(object? cell) => cell switch
    {
        double d when d == Math.Floor(d) && d is >= 1 and <= 53 => $"S{(int)d}",
        DateTime dt => ReportSchedule.WeekLabel(ReportSchedule.WeekStart(DateOnly.FromDateTime(dt))),
        _ => CellParser.Text(cell),
    };

    private static string? TimeText(object? cell) => cell switch
    {
        null => null,
        DateTime dt => dt.ToString("HH:mm", CultureInfo.InvariantCulture),
        double d when d is >= 0 and < 1 => TimeSpan.FromDays(d).ToString(@"hh\:mm", CultureInfo.InvariantCulture),
        _ => CellParser.Text(cell),
    };

    /// <summary>"S39 2026", "W39-2026", "2026-W39", "Semaine 39 2026"; a week number without a year is refused (ambiguous).</summary>
    public static DateOnly? ParseWeek(string? text)
    {
        if (text is null) return null;
        var t = text.Trim().ToLowerInvariant();
        var m = YearFirst().Match(t);
        var (year, week) = m.Success ? (int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value)) : (0, 0);
        if (!m.Success && WeekFirst().Match(t) is { Success: true } m2) (week, year) = (int.Parse(m2.Groups[1].Value), int.Parse(m2.Groups[2].Value));
        if (year is < 2000 or > 2100 || week < 1 || week > ISOWeek.GetWeeksInYear(year)) return null;
        return DateOnly.FromDateTime(ISOWeek.ToDateTime(year, week, DayOfWeek.Monday));
    }

    public static ReportStatus? ParseStatus(string text)
    {
        if (Labels.TryParse<ReportStatus>(text, out var s)) return s;
        return CellParser.Normalize(text) switch
        {
            "na" or "nonapplicable" or "sansobjet" => ReportStatus.NotApplicable,
            "recu" or "recue" or "ok" or "done" => ReportStatus.Received,
            "manquante" or "nonrecu" => ReportStatus.Missing,
            "retard" => ReportStatus.Late,
            "attente" or "todo" => ReportStatus.Pending,
            _ => null,
        };
    }

    private static bool? ParseYesNo(object? cell) => cell switch
    {
        bool b => b,
        double d when d is 0 or 1 => d == 1,
        _ => CellParser.Normalize(CellParser.Text(cell) ?? "") switch
        {
            "yes" or "y" or "oui" or "o" or "true" or "vrai" or "x" => true,
            "no" or "n" or "non" or "false" or "faux" => false,
            _ => null,
        },
    };

    [GeneratedRegex(@"^(\d{4})\D{0,3}(?:s|w|sem|semaine|week)?\s*(\d{1,2})$")]
    private static partial Regex YearFirst();

    [GeneratedRegex(@"^(?:s|w|sem|semaine|week)?\s*(\d{1,2})\D{1,3}(\d{4})$")]
    private static partial Regex WeekFirst();
}

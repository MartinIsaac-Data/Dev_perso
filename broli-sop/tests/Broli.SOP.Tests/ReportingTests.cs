using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Broli.SOP.Application.Abstractions;
using Broli.SOP.Application.Reporting;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Domain.Enums;
using ClosedXML.Excel;

namespace Broli.SOP.Tests;

public class ReportScheduleTests
{
    private static readonly DateOnly Monday = new(2026, 9, 21);

    [Theory]
    [InlineData("Friday", "2026-09-25")]
    [InlineData("vendredi", "2026-09-25")]
    [InlineData("Saturday", "2026-09-26")]
    [InlineData("Every day", "2026-09-21")]
    public void Due_date_follows_the_expected_day(string day, string expected) =>
        Assert.Equal(DateOnly.Parse(expected), ReportSchedule.Due(day, Monday));

    [Theory]
    [InlineData("To confirm")]
    [InlineData("")]
    [InlineData("whenever")]
    public void Unconfirmed_days_have_no_due_date(string day) => Assert.Null(ReportSchedule.Due(day, Monday));

    [Fact]
    public void Week_start_is_the_monday()
    {
        Assert.Equal(Monday, ReportSchedule.WeekStart(new DateOnly(2026, 9, 27)));
        Assert.Equal(Monday, ReportSchedule.WeekStart(Monday));
        Assert.Equal("S39 2026", ReportSchedule.WeekLabel(Monday));
    }

    [Fact]
    public void States_follow_dates_and_entered_status()
    {
        var friday = Monday.AddDays(4);
        var wednesday = Monday.AddDays(2);
        var nextWeek = Monday.AddDays(9);
        // Received on or before the due date: on time; after: late — whatever the status says.
        Assert.Equal(ReportState.Received, ReportSchedule.State(null, friday, friday, Monday, wednesday));
        Assert.Equal(ReportState.ReceivedLate, ReportSchedule.State(ReportStatus.Received, friday, friday.AddDays(1), Monday, nextWeek));
        Assert.Equal(ReportState.ReceivedLate, ReportSchedule.State(ReportStatus.Late, friday, friday, Monday, nextWeek));
        // Not received: pending before the due date, late after it, missing once the week is over.
        Assert.Equal(ReportState.Pending, ReportSchedule.State(null, friday, null, Monday, wednesday));
        Assert.Equal(ReportState.Late, ReportSchedule.State(null, wednesday, null, Monday, friday));
        Assert.Equal(ReportState.Missing, ReportSchedule.State(null, friday, null, Monday, nextWeek));
        // Entered statuses are respected.
        Assert.Equal(ReportState.Missing, ReportSchedule.State(ReportStatus.Missing, friday, null, Monday, wednesday));
        Assert.Equal(ReportState.NotApplicable, ReportSchedule.State(ReportStatus.NotApplicable, friday, friday.AddDays(3), Monday, nextWeek));
        Assert.Equal(ReportState.Received, ReportSchedule.State(ReportStatus.Received, friday, null, Monday, nextWeek));
        // No due date (day to confirm): pending until the week is over.
        Assert.Equal(ReportState.Pending, ReportSchedule.State(null, null, null, Monday, friday));
        Assert.Equal(3, ReportSchedule.DaysLate(ReportState.ReceivedLate, wednesday, friday.AddDays(1), Monday, nextWeek));
        Assert.Equal(2, ReportSchedule.DaysLate(ReportState.Late, wednesday, null, Monday, friday));
    }

    [Theory]
    [InlineData("S39 2026")]
    [InlineData("W39-2026")]
    [InlineData("2026-W39")]
    [InlineData("Semaine 39 2026")]
    public void Weeks_with_a_year_are_understood(string text) => Assert.Equal(Monday, ReportingWorkbook.ParseWeek(text));

    [Theory]
    [InlineData("S39")]
    [InlineData("S60 2026")]
    [InlineData("next week")]
    public void Ambiguous_weeks_are_refused(string text) => Assert.Null(ReportingWorkbook.ParseWeek(text));

    [Fact]
    public void Several_owners_are_split() =>
        Assert.Equal(["Joel Yogo", "Guillaume Tamba", "Désiré Yiamo"], ReportingService.Owners("Joel Yogo / Guillaume Tamba et Désiré Yiamo"));

    [Fact]
    public void Labels_are_french()
    {
        Assert.Equal("Vendredi", ReportSchedule.DayLabel("Friday"));
        Assert.Equal("Tous les jours", ReportSchedule.DayLabel("Every day"));
        Assert.Equal("Hebdomadaire / N3M", ReportSchedule.FrequencyLabel("Weekly / N3M"));
        Assert.Equal("À recevoir", ReportSchedule.CatalogueStatusLabel("To Receive"));
    }
}

public class ReportingWorkbookTests
{
    private static readonly DateOnly Today = new(2026, 9, 26);
    private static readonly string[] CatalogueHeaders =
        ["Reporting ID", "Department", "Reporting Name", "Owner / Preparer", "Frequency", "Expected Day", "Main Content", "Status / Current State"];
    private static readonly string[] TrackerHeaders =
        ["S&OP Week", "Reference Date", "Reporting ID", "Department", "Reporting Name", "Owner", "Expected Date", "Received Date", "Status", "Data Quality", "Relance Required", "Comments"];

    internal static NamedSheet Sheet(string name, string[] headers, params object?[][] rows) =>
        new(name, new RawSheet(headers, rows.Select((r, i) => new RawRow(i + 2, r)).ToList()));

    internal static NamedSheet Catalogue(params object?[][] rows) => Sheet("01_REPORTING_CATALOGUE", CatalogueHeaders, rows);

    private static readonly object?[] Com01 = ["COM-01", "Commercial", "Actual Sales", "Joel Yogo / Guillaume Tamba", "Weekly", "Saturday", "Sales actuals", "Identified"];
    private static readonly object?[] Wh01 = ["WH-01", "Warehouse", "Global Stock", "Fabrice Tchana", "Weekly", "Friday", null, "Received"];

    [Fact]
    public void Template_catalogue_with_an_empty_tracker_is_valid()
    {
        var o = ReportingWorkbook.Read([Catalogue(Com01, Wh01),
            Sheet("02_REPORTING_TRACKER", TrackerHeaders, [null, null, "COM-01", "Commercial", "Actual Sales", "Joel Yogo", null, null, null, null, null, null]),
            Sheet("03_REPORTING_CALENDAR", ["Day", "Department", "Reporting ID", "Reporting Name", "Owner", "Expected Time", "Purpose", "Follow-up Notes"],
                ["Friday", "Warehouse", "WH-01", "Global Stock", "Fabrice Tchana", new DateTime(1899, 12, 30, 16, 0, 0), "Stock", "Avant la réunion"])], Today);
        Assert.True(o.CanCommit, string.Join("; ", o.Issues.Select(i => i.Message)));
        Assert.Equal(2, o.Definitions.Count);
        Assert.Empty(o.Submissions);
        Assert.Equal(1, o.EmptyTrackerRows);
        var wh = o.Definitions.Single(d => d.Code == "WH-01");
        Assert.Equal(("16:00", "Stock", "Avant la réunion"), (wh.ExpectedTime, wh.Purpose, wh.FollowUpNotes));
    }

    [Fact]
    public void Filled_tracker_rows_are_read_with_french_or_english_values()
    {
        var o = ReportingWorkbook.Read([Catalogue(Com01, Wh01), Sheet("02_REPORTING_TRACKER", TrackerHeaders,
            ["S39", new DateTime(2026, 9, 26), "COM-01", null, null, null, null, new DateTime(2026, 9, 26), "Received", "OK", "No", null],
            ["S39 2026", null, "wh-01", null, null, null, "25/09/2026", null, "En retard", "Problème", "Oui", "Relancé mardi"],
            ["S38 2026", null, "WH-01", null, null, null, null, null, "Missing", null, true, null])], Today);
        Assert.True(o.CanCommit, string.Join("; ", o.Issues.Select(i => i.Message)));
        Assert.Equal(0, o.EmptyTrackerRows);
        Assert.Equal(3, o.Submissions.Count);
        var first = o.Submissions[0];
        Assert.Equal((new DateOnly(2026, 9, 21), "S39", ReportStatus.Received, ReportQuality.Ok), (first.WeekStart, first.WeekLabel, first.Status, first.Quality));
        var second = o.Submissions[1];
        Assert.Equal(("WH-01", new DateOnly(2026, 9, 21), ReportStatus.Late, ReportQuality.Issue, true, new DateOnly(2026, 9, 25)),
            (second.Code, second.WeekStart, second.Status, second.Quality, second.RelanceRequired, second.ExpectedDate));
        Assert.Equal((new DateOnly(2026, 9, 14), ReportStatus.Missing, true), (o.Submissions[2].WeekStart, o.Submissions[2].Status, o.Submissions[2].RelanceRequired));
    }

    [Fact]
    public void Tracker_errors_block_the_import()
    {
        var o = ReportingWorkbook.Read([Catalogue(Com01, Wh01), Sheet("02_REPORTING_TRACKER", TrackerHeaders,
            ["S39", null, "COM-01", null, null, null, null, null, "Received", null, null, null],
            ["S39 2026", null, "XX-99", null, null, null, null, null, "Received", null, null, null],
            ["S39 2026", null, "WH-01", null, null, null, null, "31/02/2026", "Teleported", "Great", "Maybe", null],
            ["S39 2026", null, "COM-01", null, null, null, null, new DateTime(2026, 9, 26), "Missing", null, null, null],
            ["S39 2026", null, "COM-01", null, null, null, null, null, "Pending", null, null, null],
            ["S39 2026", null, "COM-01", null, null, null, null, null, "Pending", null, null, null])], Today);
        Assert.False(o.CanCommit);
        string[] expected = ["Semaine « S39 » non reconnue", "n'est pas dans le catalogue", "Date invalide", "Statut inconnu", "Qualité inconnue",
            "non reconnue. Utilisez Yes/No", "Statut « Missing » alors qu'une date de réception", "apparaît deux fois"];
        foreach (var e in expected) Assert.Contains(o.Issues, i => i.Severity == "Error" && i.Message.Contains(e));
    }

    [Fact]
    public void Catalogue_errors_and_warnings()
    {
        var o = ReportingWorkbook.Read([Catalogue(Com01, Com01, ["X-1", null, "Name", "Owner", "Weekly", "Someday", null, null])], Today);
        Assert.Contains(o.Issues, i => i.Severity == "Error" && i.Message.Contains("déjà utilisé à la ligne 2"));
        Assert.Contains(o.Issues, i => i.Severity == "Error" && i.Message.Contains("Service manquant"));
        Assert.False(o.CanCommit);

        var missing = ReportingWorkbook.Read([Sheet("Feuil1", ["A"], ["x"])], Today);
        Assert.Contains(missing.Issues, i => i.Message.Contains("Onglet catalogue introuvable"));
        var noOwner = ReportingWorkbook.Read([Sheet("01_REPORTING_CATALOGUE", ["Reporting ID", "Department", "Reporting Name"], ["A", "B", "C"])], Today);
        Assert.Contains(noOwner.Issues, i => i.Message.Contains("Colonne obligatoire manquante : « Owner / Preparer »"));

        var unknownDay = ReportingWorkbook.Read([Catalogue(["X-1", "Dept", "Name", "Owner", "Weekly", "Someday", null, null])], Today);
        Assert.True(unknownDay.CanCommit);
        Assert.Contains(unknownDay.Issues, i => i.Severity == "Warning" && i.Message.Contains("« Someday » non reconnu"));
    }
}

public class ReportingApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    [Fact]
    public async Task Demo_dashboard_is_consistent()
    {
        var c = await factory.ClientAsync("supply");
        var d = await c.Get<ReportingDashboard>("api/reporting");
        Assert.True(d.HasDemoData);
        Assert.NotNull(d.Week);
        Assert.Equal(11, d.Weeks.Count);
        Assert.Equal(20, d.Rows.Count);
        Assert.Equal(d.Expected + d.NotApplicable, d.Received + d.ReceivedLate + d.Pending + d.Late + d.Missing + d.NotApplicable);
        Assert.Equal(d.Rows.Count, d.ByDepartment.Sum(x => x.Expected) + d.NotApplicable);
        Assert.Equal(d.Rows.Count, d.Calendar.Sum(x => x.Items.Count));
        Assert.All(d.Trend, t => Assert.True(t.ReceptionRatePct is null or >= 0 and <= 100));
        Assert.All(d.Rows, r => Assert.DoesNotContain("Friday", r.ExpectedDay));

        // A past week: nothing can still be pending.
        var past = await c.Get<ReportingDashboard>($"api/reporting?week={d.Weeks[3].WeekStart}");
        Assert.Equal(d.Weeks[3].WeekStart, past.Week!.WeekStart);
        Assert.Equal(0, past.Pending);
        Assert.True(past.Missing + past.Received + past.ReceivedLate > 0);

        var export = await c.GetAsync($"api/export/reporting?format=csv&view={d.Week!.WeekStart}");
        Assert.Equal(HttpStatusCode.OK, export.StatusCode);
        Assert.Contains("N° reporting", await export.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Reminders_notify_the_owners_and_need_edit_rights()
    {
        var supply = await factory.ClientAsync("supply");
        var d = await supply.Get<ReportingDashboard>($"api/reporting");
        var wh = d.Rows.First(r => r.Code == "WH-02");
        var r = await supply.PostAsJsonAsync("api/reporting/remind", new ReportingReminderRequest("WH-02", d.Week!.WeekStart), ApiFactory.Json);
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        var result = (await r.Content.ReadFromJsonAsync<ReportingReminderResult>(ApiFactory.Json))!;
        Assert.Equal((1, 1), (result.Reports, result.Notified));
        Assert.Empty(result.UnknownOwners);

        var warehouse = await factory.ClientAsync("warehouse");
        var feed = await warehouse.Get<NotificationFeed>("api/notifications");
        Assert.Contains(feed.Items, n => n.Title.Contains("WH-02") && n.Kind == "reporting");
        Assert.NotNull((await supply.Get<ReportingDashboard>("api/reporting")).Rows.First(x => x.Code == wh.Code).LastReminderUtc);

        // Warehouse users can read the follow-up but neither remind nor import.
        Assert.Equal(HttpStatusCode.OK, (await warehouse.GetAsync("api/reporting")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden,
            (await warehouse.PostAsJsonAsync("api/reporting/remind", new ReportingReminderRequest("WH-02", d.Week.WeekStart), ApiFactory.Json)).StatusCode);
        using var form = ReportingImportApiTests.Workbook(false);
        Assert.Equal(HttpStatusCode.Forbidden, (await supply.PostAsync("api/reporting/import/preview", form)).StatusCode);
    }
}

public class ReportingImportApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    internal static MultipartFormDataContent Workbook(bool withError)
    {
        using var wb = new XLWorkbook();
        var cat = wb.Worksheets.Add("01_REPORTING_CATALOGUE");
        string[] h = ["Reporting ID", "Department", "Reporting Name", "Owner / Preparer", "Frequency", "Expected Day", "Main Content", "Status / Current State"];
        for (var i = 0; i < h.Length; i++) cat.Cell(1, i + 1).Value = h[i];
        object[][] rows =
        [
            ["COM-01", "Commercial", "Actual Sales", "Responsable commercial (DÉMO) / Joel Yogo", "Weekly", "Saturday", "Sales actuals", "Identified"],
            ["WH-01", "Warehouse", "Global Stock – FG Imported", "Fabrice Tchana", "Weekly", "Friday", "Stock", "Received"],
            ["FIN-03", "Finance", "Document Withdrawal", "Marlène TOUDJI", "Weekly", "Every day", "Documents", "To Receive"],
        ];
        for (var r = 0; r < rows.Length; r++) for (var c = 0; c < rows[r].Length; c++) cat.Cell(r + 2, c + 1).Value = rows[r][c].ToString();

        var tr = wb.Worksheets.Add("02_REPORTING_TRACKER");
        string[] t = ["S&OP Week", "Reference Date", "Reporting ID", "Department", "Reporting Name", "Owner", "Expected Date", "Received Date", "Status", "Data Quality", "Relance Required", "Comments"];
        for (var i = 0; i < t.Length; i++) tr.Cell(1, i + 1).Value = t[i];
        tr.Cell(2, 1).Value = "S38"; tr.Cell(2, 2).Value = new DateTime(2026, 9, 19); tr.Cell(2, 3).Value = "COM-01";
        tr.Cell(2, 8).Value = new DateTime(2026, 9, 19); tr.Cell(2, 9).Value = "Received"; tr.Cell(2, 10).Value = "OK"; tr.Cell(2, 11).Value = "No";
        tr.Cell(3, 1).Value = "S38"; tr.Cell(3, 2).Value = new DateTime(2026, 9, 19); tr.Cell(3, 3).Value = withError ? "ZZ-01" : "WH-01";
        tr.Cell(3, 9).Value = "Missing"; tr.Cell(3, 11).Value = "Yes"; tr.Cell(3, 12).Value = "Pas reçu";
        tr.Cell(4, 3).Value = "FIN-03"; // template row, not filled in yet

        var stream = new MemoryStream();
        wb.SaveAs(stream);
        stream.Position = 0;
        var form = new MultipartFormDataContent();
        var file = new StreamContent(stream);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        form.Add(file, "file", "SOP_Reporting_Catalogue.xlsx");
        return form;
    }

    [Fact]
    public async Task Workbook_import_replaces_the_demo_and_rejects_errors()
    {
        var c = await factory.ClientAsync();

        using var bad = Workbook(true);
        var badPreview = (await (await c.PostAsync("api/reporting/import/preview", bad)).Content.ReadFromJsonAsync<ReportingImportPreview>(ApiFactory.Json))!;
        Assert.False(badPreview.CanCommit);
        Assert.Contains(badPreview.Issues, i => i.Message.Contains("« ZZ-01 » n'est pas dans le catalogue"));
        var refused = await c.PostAsync($"api/reporting/import/{badPreview.Id}/commit", null);
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        Assert.True((await c.Get<ReportingDashboard>("api/reporting")).HasDemoData); // nothing imported

        using var good = Workbook(false);
        var preview = (await (await c.PostAsync("api/reporting/import/preview", good)).Content.ReadFromJsonAsync<ReportingImportPreview>(ApiFactory.Json))!;
        Assert.True(preview.CanCommit, string.Join("; ", preview.Issues.Select(i => i.Message)));
        Assert.Equal((3, 2, 1, true), (preview.Reports, preview.TrackerRows, preview.EmptyTrackerRows, preview.WillReplaceDemo));
        var commit = await c.PostAsync($"api/reporting/import/{preview.Id}/commit", null);
        Assert.True(commit.IsSuccessStatusCode, await commit.Content.ReadAsStringAsync());
        var result = (await commit.Content.ReadFromJsonAsync<ReportingImportResult>(ApiFactory.Json))!;
        Assert.True(result.ReplacedDemo);

        var week = await c.Get<ReportingDashboard>("api/reporting?week=2026-09-14");
        Assert.False(week.HasDemoData);
        Assert.Equal(3, week.Catalogue.Count);
        Assert.Equal("Hebdomadaire", week.Catalogue[0].Frequency);
        Assert.Equal(nameof(ReportState.Received), week.Rows.Single(r => r.Code == "COM-01").StateKey);
        var wh = week.Rows.Single(r => r.Code == "WH-01");
        Assert.Equal((nameof(ReportState.Missing), true, "Pas reçu"), (wh.StateKey, wh.RelanceRequired, wh.Comments));
        Assert.Contains(week.Weeks, w => w.Label.StartsWith("S38"));

        // Re-importing the same file updates the catalogue in place.
        using var smaller = Workbook(false);
        var p2 = (await (await c.PostAsync("api/reporting/import/preview", smaller)).Content.ReadFromJsonAsync<ReportingImportPreview>(ApiFactory.Json))!;
        Assert.Equal((0, 3), (p2.NewReports, p2.UpdatedReports));

        var history = await c.Get<List<ImportBatchDto>>("api/imports/history");
        Assert.Contains(history, b => b.Type == "Suivi des reportings" && b.Status == "Committed");
    }
}

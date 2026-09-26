using System.Globalization;
using Broli.SOP.Application.Import;

namespace Broli.SOP.Application.Reporting;

public enum ScheduleKind { None, Weekly, Daily, ToConfirm, Unknown }

public readonly record struct Schedule(ScheduleKind Kind, DayOfWeek Day);

/// <summary>Due dates and statuses of weekly reports. S&amp;OP weeks run Monday to Sunday.</summary>
public static class ReportSchedule
{
    private static readonly CultureInfo Fr = CultureInfo.GetCultureInfo("fr-FR");

    public static Schedule Parse(string? expectedDay)
    {
        var key = CellParser.Normalize(expectedDay ?? "");
        return key switch
        {
            "" => new(ScheduleKind.None, default),
            "monday" or "lundi" or "mon" or "lun" => new(ScheduleKind.Weekly, DayOfWeek.Monday),
            "tuesday" or "mardi" or "tue" or "mar" => new(ScheduleKind.Weekly, DayOfWeek.Tuesday),
            "wednesday" or "mercredi" or "wed" or "mer" => new(ScheduleKind.Weekly, DayOfWeek.Wednesday),
            "thursday" or "jeudi" or "thu" or "jeu" => new(ScheduleKind.Weekly, DayOfWeek.Thursday),
            "friday" or "vendredi" or "fri" or "ven" => new(ScheduleKind.Weekly, DayOfWeek.Friday),
            "saturday" or "samedi" or "sat" or "sam" => new(ScheduleKind.Weekly, DayOfWeek.Saturday),
            "sunday" or "dimanche" or "sun" or "dim" => new(ScheduleKind.Weekly, DayOfWeek.Sunday),
            "everyday" or "daily" or "touslesjours" or "quotidien" or "chaquejour" => new(ScheduleKind.Daily, default),
            "toconfirm" or "tbc" or "aconfirmer" or "tbd" => new(ScheduleKind.ToConfirm, default),
            _ => new(ScheduleKind.Unknown, default),
        };
    }

    public static DateOnly WeekStart(DateOnly date) => date.AddDays(-(((int)date.DayOfWeek + 6) % 7));

    public static string WeekLabel(DateOnly weekStart) =>
        $"S{ISOWeek.GetWeekOfYear(weekStart.ToDateTime(TimeOnly.MinValue)):00} {ISOWeek.GetYear(weekStart.ToDateTime(TimeOnly.MinValue))}";

    /// <summary>Due date of a report in a week: its weekday; a daily report is first due on Monday; unconfirmed days have none.</summary>
    public static DateOnly? Due(string? expectedDay, DateOnly weekStart) => Parse(expectedDay) switch
    {
        { Kind: ScheduleKind.Weekly, Day: var d } => weekStart.AddDays(((int)d + 6) % 7),
        { Kind: ScheduleKind.Daily } => weekStart,
        _ => null,
    };

    /// <summary>
    /// What the portal shows. A received date always wins (late when after the due date). Without one, the status entered in
    /// the tracker is kept (Late with a received date means received late); otherwise a report past its due date is late,
    /// and once the week is over it is missing.
    /// </summary>
    public static ReportState State(ReportStatus? status, DateOnly? due, DateOnly? received, DateOnly weekStart, DateOnly today)
    {
        if (status == ReportStatus.NotApplicable) return ReportState.NotApplicable;
        if (received is { } r)
            return status == ReportStatus.Late || due is { } d && r > d ? ReportState.ReceivedLate : ReportState.Received;
        switch (status)
        {
            case ReportStatus.Received: return ReportState.Received;
            case ReportStatus.Missing: return ReportState.Missing;
            case ReportStatus.Late: return ReportState.Late;
        }
        if (today > weekStart.AddDays(6)) return ReportState.Missing;
        return due is { } dd && dd < today ? ReportState.Late : ReportState.Pending;
    }

    /// <summary>Days of delay: received after the due date, or still outstanding (counted up to today, at most the end of the week).</summary>
    public static int? DaysLate(ReportState state, DateOnly? due, DateOnly? received, DateOnly weekStart, DateOnly today)
    {
        if (due is not { } d) return null;
        var end = state switch
        {
            ReportState.ReceivedLate => received,
            ReportState.Late or ReportState.Missing => today < weekStart.AddDays(6) ? today : weekStart.AddDays(6),
            _ => null,
        };
        return end is { } e && e.DayNumber > d.DayNumber ? e.DayNumber - d.DayNumber : null;
    }

    /// <summary>French display of the expected day ("Friday" → "Vendredi", "Every day" → "Tous les jours"); unknown text is kept.</summary>
    public static string DayLabel(string? expectedDay) => Parse(expectedDay) switch
    {
        { Kind: ScheduleKind.Weekly, Day: var d } => DayName(d),
        { Kind: ScheduleKind.Daily } => "Tous les jours",
        { Kind: ScheduleKind.ToConfirm } => "À confirmer",
        _ => expectedDay ?? "",
    };

    /// <summary>"Weekly / N3M" → "Hebdomadaire / N3M".</summary>
    public static string FrequencyLabel(string? frequency) => string.Join(" / ", (frequency ?? "").Split('/').Select(p => p.Trim()).Select(p =>
        CellParser.Normalize(p) switch
        {
            "weekly" => "Hebdomadaire",
            "daily" => "Quotidien",
            "monthly" => "Mensuel",
            "biweekly" or "fortnightly" => "Bimensuel",
            "quarterly" => "Trimestriel",
            "yearly" or "annual" => "Annuel",
            _ => p,
        }));

    /// <summary>Catalogue state ("Identified", "Received", "To Receive") in French; unknown text is kept.</summary>
    public static string? CatalogueStatusLabel(string? status) => status is null ? null : CellParser.Normalize(status) switch
    {
        "identified" => "Identifié",
        "received" => "Reçu",
        "toreceive" => "À recevoir",
        "validated" => "Validé",
        "pending" => "En attente",
        _ => status,
    };

    public static string DayName(DayOfWeek day) => Capitalise(Fr.DateTimeFormat.GetDayName(day));

    public static string Capitalise(string s) => s.Length == 0 ? s : char.ToUpper(s[0], Fr) + s[1..];
}

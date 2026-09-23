namespace Broli.SOP.Contracts.Dtos;

public record Option(string Value, string Label, string? Group = null);

/// <summary>A labelled value for charts. <see cref="Key"/> is the business key used for drill-down.</summary>
public record ChartPoint(string Label, double? Value, string? Key = null);

public record ChartSeries(string Name, IReadOnlyList<ChartPoint> Points);

/// <summary>The period the server actually resolved from the filter.</summary>
public record PeriodInfo(
    string Label,
    int Year,
    IReadOnlyList<int> Months,
    DateOnly AsOfMonth,
    DateOnly PeriodStart,
    DateOnly PeriodEnd,
    string? PreviousLabel);

/// <summary>
/// One executive KPI tile. Values are always finite or null — never NaN/Infinity.
/// <see cref="Status"/> is one of good / watch / bad / neutral.
/// </summary>
public record KpiCard(
    string Code,
    string Title,
    double? Value,
    string Format,
    string? Unit,
    double? PreviousValue,
    double? ChangePct,
    bool HigherIsBetter,
    string Status,
    string? Subtitle,
    string DrillUrl);

public record ApiError(string Message, IReadOnlyList<string>? Details = null);

namespace Broli.SOP.Contracts.Dtos;

public record DemandSummary(
    double Forecast,
    double Actual,
    double Variance,
    double? VariancePct,
    double? AccuracyPct,
    double? BiasPct,
    int OnTrack,
    int UnderForecast,
    int OverForecast);

public record DemandDashboard(
    PeriodInfo Period,
    DemandSummary Summary,
    string Unit,
    IReadOnlyList<string> TrendMonths,
    IReadOnlyList<double?> TrendForecast,
    IReadOnlyList<double?> TrendActual,
    IReadOnlyList<double?> TrendAccuracy,
    IReadOnlyList<ChartPoint> WorstAccuracyByProduct,
    IReadOnlyList<ChartPoint> BiasByFamily,
    double TolerancePct,
    double AccuracyTargetPct);

public record DemandRow(
    string CArtSap,
    string Description,
    string Category,
    string? Brand,
    string Unit,
    double Forecast,
    double Actual,
    double Variance,
    double? VariancePct,
    double? AccuracyPct,
    double? BiasPct,
    string Status);

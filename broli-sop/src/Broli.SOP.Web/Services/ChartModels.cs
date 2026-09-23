namespace Broli.SOP.Web.Services;

/// <summary>One series handed to Chart.js. Colours are CSS custom properties (e.g. "--series-1") so themes apply.</summary>
public sealed record ChartDataset(
    string Label,
    IReadOnlyList<double?> Data,
    string Color,
    string? Type = null,
    IReadOnlyList<string>? PointColors = null,
    bool Dashed = false);

public readonly record struct ChartClick(int DatasetIndex, int Index);

public static class StatusColors
{
    public static string For(string? status) => Fmt.StatusClass(status) switch
    {
        "st-critical" => "--critical",
        "st-serious" => "--serious",
        "st-warning" => "--warning",
        "st-good" => "--good",
        "st-excess" => "--excess",
        _ => "--axis",
    };
}

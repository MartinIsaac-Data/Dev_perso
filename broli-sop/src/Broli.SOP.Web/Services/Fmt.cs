using System.Globalization;

namespace Broli.SOP.Web.Services;

/// <summary>Display formatting. Null, NaN and Infinity always render as an em dash — never as "NaN".</summary>
public static class Fmt
{
    private static readonly CultureInfo Culture = CultureInfo.GetCultureInfo("en-US");
    public const string Empty = "—";

    private static bool Ok(double? v) => v is { } x && double.IsFinite(x);

    public static string Num(double? v, int decimals = 0) => Ok(v) ? v!.Value.ToString("N" + decimals, Culture) : Empty;

    /// <summary>Compact: 1.2k, 3.4M.</summary>
    public static string Compact(double? v)
    {
        if (!Ok(v)) return Empty;
        var x = v!.Value;
        var a = Math.Abs(x);
        return a >= 1e9 ? (x / 1e9).ToString("0.#", Culture) + "B"
            : a >= 1e6 ? (x / 1e6).ToString("0.#", Culture) + "M"
            : a >= 1e4 ? (x / 1e3).ToString("0.#", Culture) + "k"
            : x.ToString(a >= 100 ? "N0" : "0.#", Culture);
    }

    public static string Pct(double? v, int decimals = 1) => Ok(v) ? v!.Value.ToString("N" + decimals, Culture) + "%" : Empty;
    public static string SignedPct(double? v, int decimals = 1) => Ok(v) ? (v > 0 ? "+" : "") + v!.Value.ToString("N" + decimals, Culture) + "%" : Empty;
    public static string Months(double? v) => Ok(v) ? v!.Value.ToString("0.0", Culture) + " mo" : Empty;
    public static string Date(DateOnly? d) => d is { } x ? x.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture) : Empty;
    public static string DateShort(DateOnly? d) => d is { } x ? x.ToString("dd MMM", Culture) : Empty;
    public static string DateTime(System.DateTime? d) => d is { } x ? x.ToLocalTime().ToString("dd/MM/yyyy HH:mm", CultureInfo.InvariantCulture) : Empty;

    public static string Kpi(double? v, string format) => format switch
    {
        "percent" => Pct(v),
        "signedPercent" => SignedPct(v),
        "months" => Ok(v) ? v!.Value.ToString("0.0", Culture) : Empty,
        "integer" => Num(v),
        _ => Ok(v) && Math.Abs(v!.Value) < 100 ? Num(v, 1) : Num(v),
    };

    /// <summary>CSS class for a business status label (coverage, risk, severity, forecast status…).</summary>
    public static string StatusClass(string? status) => (status ?? "").ToLowerInvariant() switch
    {
        "critical" => "st-critical",
        "risk" or "supply risk" or "high" or "under forecast" or "overdue" => "st-serious",
        "watch" or "medium" or "over forecast" or "in progress" => "st-warning",
        "normal" or "ok" or "on track" or "good" or "delivered" or "closed" => "st-good",
        "excess" => "st-excess",
        _ => "st-neutral",
    };

    public static string StatusIcon(string? status) => StatusClass(status) switch
    {
        "st-critical" => "✖",
        "st-serious" => "▲",
        "st-warning" => "◆",
        "st-good" => "✔",
        "st-excess" => "■",
        _ => "●",
    };
}

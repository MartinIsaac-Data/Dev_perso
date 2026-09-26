using System.Globalization;
using System.Text;

namespace Broli.SOP.Application.Import;

/// <summary>Tolerant conversion of raw Excel cells (French or international formats) into typed values.</summary>
public static class CellParser
{
    private static readonly string[] DateFormats =
    [
        "dd/MM/yyyy", "d/M/yyyy", "dd/MM/yy", "yyyy-MM-dd", "dd-MM-yyyy", "dd.MM.yyyy", "yyyy/MM/dd",
        "dd/MM/yyyy HH:mm:ss", "yyyy-MM-ddTHH:mm:ss", "yyyy-MM-dd HH:mm:ss",
    ];
    private static readonly string[] MonthFormats = ["yyyy-MM", "MM/yyyy", "M/yyyy", "MMM yyyy", "MMMM yyyy", "yyyyMM"];

    public static string Normalize(string header)
    {
        var decomposed = header.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (var c in decomposed)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark && char.IsLetterOrDigit(c)) sb.Append(c);
        return sb.ToString();
    }

    public static bool IsBlank(object? cell) => cell is null || cell is string s && string.IsNullOrWhiteSpace(s);

    public static string? Text(object? cell) => cell switch
    {
        null => null,
        string s => string.IsNullOrWhiteSpace(s) ? null : s.Trim(),
        double d when d == Math.Floor(d) && Math.Abs(d) < 1e15 => ((long)d).ToString(CultureInfo.InvariantCulture),
        double d => d.ToString(CultureInfo.InvariantCulture),
        DateTime dt => dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
        _ => cell.ToString()?.Trim(),
    };

    public static bool TryNumber(object? cell, out double value)
    {
        value = 0;
        switch (cell)
        {
            case double d when !double.IsNaN(d) && !double.IsInfinity(d):
                value = d;
                return true;
            case int i:
                value = i;
                return true;
            case string s:
                var t = s.Trim().Replace(" ", "").Replace(" ", "").Replace(" ", "");
                if (t.Contains(',') && !t.Contains('.')) t = t.Replace(',', '.');
                else if (t.Contains(',') && t.Contains('.')) t = t.Replace(",", "");
                return double.TryParse(t, NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                       && !double.IsNaN(value) && !double.IsInfinity(value);
            default:
                return false;
        }
    }

    public static bool TryDate(object? cell, out DateOnly value)
    {
        value = default;
        switch (cell)
        {
            case DateTime dt:
                value = DateOnly.FromDateTime(dt);
                return Plausible(value);
            case double d when d is > 20000 and < 80000:
                value = DateOnly.FromDateTime(DateTime.FromOADate(d));
                return Plausible(value);
            case string s:
                var t = s.Trim();
                if (DateTime.TryParseExact(t, DateFormats, CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsed))
                {
                    value = DateOnly.FromDateTime(parsed);
                    return Plausible(value);
                }
                return false;
            default:
                return false;
        }
    }

    /// <summary>A month, given as any date inside it or as "2026-09", "09/2026", "Sep 2026".</summary>
    public static bool TryMonth(object? cell, out DateOnly monthStart)
    {
        monthStart = default;
        if (TryDate(cell, out var d))
        {
            monthStart = new DateOnly(d.Year, d.Month, 1);
            return true;
        }
        var t = Text(cell);
        if (t is null) return false;
        foreach (var culture in new[] { CultureInfo.InvariantCulture, CultureInfo.GetCultureInfo("fr-FR") })
            if (DateTime.TryParseExact(t, MonthFormats, culture, DateTimeStyles.None, out var parsed))
            {
                monthStart = new DateOnly(parsed.Year, parsed.Month, 1);
                return Plausible(monthStart);
            }
        return false;
    }

    private static bool Plausible(DateOnly d) => d.Year is >= 2000 and <= 2100;

    public static MaterialType? ParseMaterialType(string? text)
    {
        if (text is null) return null;
        var n = Normalize(text);
        return n switch
        {
            "finishedgood" or "finishedgoods" or "fg" or "pf" or "produitfini" or "produitsfinis" => MaterialType.FinishedGood,
            "rawmaterial" or "rawmaterials" or "rm" or "mp" or "matierepremiere" or "matierespremieres" => MaterialType.RawMaterial,
            "packaging" or "pkg" or "film" or "films" or "emballage" or "emballages" => MaterialType.Packaging,
            _ => null,
        };
    }

    public static SupplyStatus? ParseStatus(string? text)
    {
        if (text is null) return null;
        if (Labels.TryParse<SupplyStatus>(text, out var s)) return s;
        return Normalize(text) switch
        {
            "planifie" or "plan" => SupplyStatus.Planned,
            "confirme" or "confirmed" => SupplyStatus.Confirmed,
            "enproduction" or "production" => SupplyStatus.InProduction,
            "pret" or "ready" => SupplyStatus.Ready,
            "expedie" or "embarque" or "shipped" or "intransit" or "transit" => SupplyStatus.Shipped,
            "auport" or "port" or "atport" => SupplyStatus.AtPort,
            "douane" or "customs" or "clearing" or "dedouanement" => SupplyStatus.Customs,
            "livre" or "recu" or "received" or "delivered" => SupplyStatus.Delivered,
            "retard" or "enretard" or "late" => SupplyStatus.Delayed,
            "annule" or "cancelled" or "canceled" => SupplyStatus.Cancelled,
            _ => null,
        };
    }
}

using System.Text;

namespace Broli.SOP.Application;

/// <summary>Human-readable labels for enums, and tolerant parsing back from labels.</summary>
public static class Labels
{
    public static string Of(CoverageStatus s) => s == CoverageStatus.NoDemand ? "No Demand" : s.ToString();
    public static string Of(EtaRiskLevel l) => l == EtaRiskLevel.None ? "OK" : Spaced(l.ToString());
    public static string Of<T>(T value) where T : struct, Enum => Spaced(value.ToString());

    public static string Spaced(string name)
    {
        var sb = new StringBuilder(name.Length + 4);
        for (var i = 0; i < name.Length; i++)
        {
            if (i > 0 && char.IsUpper(name[i]) && !char.IsUpper(name[i - 1])) sb.Append(' ');
            sb.Append(name[i]);
        }
        return sb.ToString();
    }

    public static bool TryParse<T>(string? text, out T value) where T : struct, Enum
    {
        value = default;
        if (string.IsNullOrWhiteSpace(text)) return false;
        var compact = new string(text.Where(char.IsLetterOrDigit).ToArray());
        return Enum.TryParse(compact, true, out value) && Enum.IsDefined(value);
    }
}

using Broli.SOP.Contracts.Settings;

namespace Broli.SOP.Application.Calculations;

/// <summary>Converts base-unit quantities into 20' containers (TC).</summary>
public static class TcConverter
{
    /// <summary>Base units per TC for a product, or null when no conversion is known.</summary>
    public static double? UnitsPerTc(double? productQtyPerTc, string baseUnit, TcSettings settings)
    {
        if (productQtyPerTc is { } q && q > 0) return q;
        if (string.Equals(baseUnit, "KG", StringComparison.OrdinalIgnoreCase) && settings.DefaultKgPerTc > 0)
            return settings.DefaultKgPerTc;
        return null;
    }

    public static double? ToTc(double quantity, double? unitsPerTc) =>
        unitsPerTc is { } u && u > 0 ? KpiMath.Finite(quantity / u) : null;

    public static double KgToTc(double kg, TcSettings settings) =>
        settings.DefaultKgPerTc > 0 ? kg / settings.DefaultKgPerTc : 0;
}

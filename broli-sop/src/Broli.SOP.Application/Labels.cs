using System.Globalization;
using System.Text;

namespace Broli.SOP.Application;

/// <summary>
/// French display labels for enums, and tolerant parsing back from a label. Parsing accepts the French label, the enum
/// name and its spaced English form ("Shipped", "At Port", "AtPort"), so imported files and older clients keep working.
/// </summary>
public static class Labels
{
    private static readonly Dictionary<Type, Dictionary<string, string>> French = new()
    {
        [typeof(MaterialType)] = new()
        {
            ["FinishedGood"] = "Produit fini", ["RawMaterial"] = "Matière première", ["Packaging"] = "Emballage",
        },
        [typeof(SupplyStatus)] = new()
        {
            ["Planned"] = "Planifié", ["Confirmed"] = "Confirmé", ["InProduction"] = "En production", ["Ready"] = "Prêt",
            ["Shipped"] = "Expédié", ["AtPort"] = "Au port", ["Customs"] = "En douane", ["Delivered"] = "Livré",
            ["Delayed"] = "Retardé", ["Cancelled"] = "Annulé",
        },
        [typeof(CoverageStatus)] = new()
        {
            ["NoDemand"] = "Sans demande", ["Critical"] = "Critique", ["Risk"] = "Risque", ["Watch"] = "À surveiller",
            ["Normal"] = "Normal", ["Excess"] = "Excédent",
        },
        [typeof(ForecastStatus)] = new()
        {
            ["NoData"] = "Sans données", ["OnTrack"] = "Conforme", ["UnderForecast"] = "Sous la prévision",
            ["OverForecast"] = "Au-dessus de la prévision",
        },
        [typeof(EtaRiskLevel)] = new()
        {
            ["None"] = "OK", ["Watch"] = "À surveiller", ["SupplyRisk"] = "Risque appro", ["Critical"] = "Critique",
        },
        [typeof(RiskCategory)] = new()
        {
            ["Stockout"] = "Rupture", ["Overstock"] = "Surstock", ["SupplyDelay"] = "Retard fournisseur",
            ["PortDelay"] = "Retard au port", ["Customs"] = "Douane", ["ForecastRisk"] = "Risque prévision",
            ["SupplierRisk"] = "Risque fournisseur", ["ProductionRisk"] = "Risque production",
            ["DemandIncrease"] = "Hausse de la demande", ["ExcessStock"] = "Stock excédentaire",
        },
        [typeof(RiskStatus)] = new() { ["Open"] = "Ouvert", ["InProgress"] = "En cours", ["Closed"] = "Clos" },
        [typeof(ImpactLevel)] = new() { ["Low"] = "Faible", ["Medium"] = "Moyen", ["High"] = "Élevé", ["Critical"] = "Critique" },
        [typeof(ImportType)] = new()
        {
            ["ProductMaster"] = "Référentiel produits", ["SupplierMaster"] = "Référentiel fournisseurs", ["Sales"] = "Ventes",
            ["Inventory"] = "Stocks", ["Supply"] = "Approvisionnements", ["Forecast"] = "Prévisions",
        },
        [typeof(ImportStatus)] = new() { ["Validated"] = "Validé", ["Committed"] = "Importé", ["Rejected"] = "Rejeté", ["Failed"] = "Échec" },
        [typeof(ActionStatus)] = new() { ["Open"] = "Ouverte", ["InProgress"] = "En cours", ["Done"] = "Terminée", ["Cancelled"] = "Annulée" },
        [typeof(ActionPriority)] = new() { ["Low"] = "Basse", ["Medium"] = "Moyenne", ["High"] = "Haute", ["Critical"] = "Critique" },
        [typeof(DataSourceKind)] = new() { ["ExcelFolder"] = "Dossier Excel", ["SqlStaging"] = "Table SQL de staging" },
        [typeof(Contracts.Settings.ConsumptionBasis)] = new()
        {
            ["Forecast"] = "Prévision", ["History"] = "Historique", ["MaxOfBoth"] = "Maximum des deux",
        },
    };

    public static string Of<T>(T value) where T : struct, Enum =>
        French.TryGetValue(typeof(T), out var map) && map.TryGetValue(value.ToString(), out var label) ? label : Spaced(value.ToString());

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
        var key = Key(text);
        if (French.TryGetValue(typeof(T), out var map))
        {
            foreach (var (name, label) in map)
                if (Key(label) == key && Enum.TryParse(name, out value)) return true;
        }
        return Enum.TryParse(key, true, out value) && Enum.IsDefined(value);
    }

    /// <summary>True when <paramref name="text"/> is a label (French or English) of <paramref name="value"/>.</summary>
    public static bool Is<T>(string? text, T value) where T : struct, Enum =>
        TryParse<T>(text, out var parsed) && parsed.Equals(value);

    /// <summary>The enum's numeric value for a label, or <paramref name="fallback"/> when it is not one: used to sort by severity.</summary>
    public static int Rank<T>(string? text, int fallback = 0) where T : struct, Enum =>
        TryParse<T>(text, out var parsed) ? Convert.ToInt32(parsed) : fallback;

    /// <summary>Letters and digits only, lower case, accents removed: "À surveiller" and "a-surveiller" compare equal.</summary>
    private static string Key(string text)
    {
        var decomposed = text.Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(decomposed.Length);
        foreach (var c in decomposed)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark && char.IsLetterOrDigit(c))
                sb.Append(char.ToLowerInvariant(c));
        return sb.ToString();
    }
}

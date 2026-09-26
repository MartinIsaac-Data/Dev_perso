using System.Text.Json;

namespace Broli.SOP.Application.Services;

public sealed class SettingsService(ISettingsStore store, IAuditLogger audit, IDataVersion version, ICurrentUser user)
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = false };

    public async Task<SettingsDto> GetAsync(CancellationToken ct)
    {
        var s = await store.GetAsync(ct);
        return new SettingsDto(s.Coverage, s.SafetyStock, s.Forecast, s.Supply, s.Tc, s.General, s.AlertRules);
    }

    public async Task SaveAsync(SettingsDto dto, CancellationToken ct)
    {
        Validate(dto);
        var before = await store.GetAsync(ct);
        var after = new SopSettings(dto.Coverage, dto.SafetyStock, dto.Forecast, dto.Supply, dto.Tc, dto.General, dto.Alerts ?? before.AlertRules);
        await store.SaveAsync(after, user.Username, ct);

        var changes = new List<(string Section, string Old, string New)>();
        void Diff<T>(string section, T oldValue, T newValue)
        {
            var o = JsonSerializer.Serialize(oldValue, Json);
            var n = JsonSerializer.Serialize(newValue, Json);
            if (o != n) changes.Add((section, o, n));
        }
        Diff(CoverageSettings.Key, before.Coverage, after.Coverage);
        Diff(SafetyStockSettings.Key, before.SafetyStock, after.SafetyStock);
        Diff(ForecastSettings.Key, before.Forecast, after.Forecast);
        Diff(SupplySettings.Key, before.Supply, after.Supply);
        Diff(TcSettings.Key, before.Tc, after.Tc);
        Diff(GeneralSettings.Key, before.General, after.General);
        Diff(AlertSettings.Key, before.AlertRules, after.AlertRules);
        foreach (var c in changes)
            await audit.LogAsync("Configuration modifiée", "Configuration", c.Section, c.Old, c.New, ct);
        version.Bump();
    }

    public static void Validate(SettingsDto s)
    {
        var e = new List<string>();
        var c = s.Coverage;
        if (c.AverageMonths is < 1 or > 24) e.Add("Coverage: averaging window must be 1–24 months.");
        if (!(c.CriticalBelowMonths > 0 && c.CriticalBelowMonths < c.RiskBelowMonths && c.RiskBelowMonths < c.WatchBelowMonths && c.WatchBelowMonths < c.ExcessAboveMonths))
            e.Add("Les seuils de couverture doivent être croissants : Critique < Risque < À surveiller < Excédent.");
        if (s.SafetyStock.DefaultMonths < 0 || s.SafetyStock.MonthsByCategory.Values.Any(v => v < 0)) e.Add("Les mois de stock de sécurité ne peuvent pas être négatifs.");
        if (s.Forecast.OnTrackTolerancePct is < 0 or > 100) e.Add("La tolérance de prévision doit être comprise entre 0 et 100 %.");
        if (s.Forecast.HorizonMonths is < 1 or > 24) e.Add("L'horizon de prévision doit être compris entre 1 et 24 mois.");
        if (s.Forecast.AccuracyTargetPct is < 0 or > 100 || s.Forecast.ServiceLevelTargetPct is < 0 or > 100) e.Add("Les objectifs doivent être compris entre 0 et 100 %.");
        if (s.Supply.WatchWindowDays is < 0 or > 90) e.Add("La fenêtre de surveillance doit être comprise entre 0 et 90 jours.");
        if (s.Supply.InFullTolerancePct is < 0 or > 100 || s.Supply.OtifTargetPct is < 0 or > 100) e.Add("Les pourcentages d'approvisionnement doivent être compris entre 0 et 100 %.");
        if (s.Supply.TransitDaysByCountry.Values.Any(v => v is < 0 or > 365)) e.Add("Les jours de transit doivent être compris entre 0 et 365.");
        if (s.Tc.DefaultKgPerTc <= 0) e.Add("Les kg par TC doivent être positifs.");
        if (s.Supply.PortToWarehouseDays is < 0 or > 60) e.Add("Le délai port → entrepôt doit être compris entre 0 et 60 jours.");
        if (s.Supply.SupplierOnTimeAlertPct is < 0 or > 100) e.Add("L'alerte fournisseur doit être comprise entre 0 et 100 %.");
        if (s.Coverage.SlowMovingMonths is < 1 or > 24) e.Add("La fenêtre de rotation lente doit être comprise entre 1 et 24 mois.");
        if (string.IsNullOrWhiteSpace(s.General.Currency) || s.General.Currency.Length > 5) e.Add("Le code devise est obligatoire (5 caractères maximum).");
        if (s.General.FiscalYearStartMonth is < 1 or > 12) e.Add("Le mois de début d'exercice doit être compris entre 1 et 12.");
        if (s.Alerts is { RepeatAfterDays: < 0 or > 90 }) e.Add("Le délai de répétition des alertes doit être compris entre 0 et 90 jours.");
        if (e.Count > 0) throw new ValidationException(e);
    }
}

using System.Text.Json;

namespace Broli.SOP.Application.Services;

public sealed class SettingsService(ISettingsStore store, IAuditLogger audit, IDataVersion version, ICurrentUser user)
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = false };

    public async Task<SettingsDto> GetAsync(CancellationToken ct)
    {
        var s = await store.GetAsync(ct);
        return new SettingsDto(s.Coverage, s.SafetyStock, s.Forecast, s.Supply, s.Tc, s.General);
    }

    public async Task SaveAsync(SettingsDto dto, CancellationToken ct)
    {
        Validate(dto);
        var before = await store.GetAsync(ct);
        var after = new SopSettings(dto.Coverage, dto.SafetyStock, dto.Forecast, dto.Supply, dto.Tc, dto.General);
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
        foreach (var c in changes)
            await audit.LogAsync("Updated configuration", "Configuration", c.Section, c.Old, c.New, ct);
        version.Bump();
    }

    public static void Validate(SettingsDto s)
    {
        var e = new List<string>();
        var c = s.Coverage;
        if (c.AverageMonths is < 1 or > 24) e.Add("Coverage: averaging window must be 1–24 months.");
        if (!(c.CriticalBelowMonths > 0 && c.CriticalBelowMonths < c.RiskBelowMonths && c.RiskBelowMonths < c.WatchBelowMonths && c.WatchBelowMonths < c.ExcessAboveMonths))
            e.Add("Coverage thresholds must increase: Critical < Risk < Watch < Excess.");
        if (s.SafetyStock.DefaultMonths < 0 || s.SafetyStock.MonthsByCategory.Values.Any(v => v < 0)) e.Add("Safety stock months cannot be negative.");
        if (s.Forecast.OnTrackTolerancePct is < 0 or > 100) e.Add("Forecast tolerance must be 0–100 %.");
        if (s.Forecast.HorizonMonths is < 1 or > 24) e.Add("Forecast horizon must be 1–24 months.");
        if (s.Forecast.AccuracyTargetPct is < 0 or > 100 || s.Forecast.ServiceLevelTargetPct is < 0 or > 100) e.Add("Targets must be 0–100 %.");
        if (s.Supply.WatchWindowDays is < 0 or > 90) e.Add("Watch window must be 0–90 days.");
        if (s.Supply.InFullTolerancePct is < 0 or > 100 || s.Supply.OtifTargetPct is < 0 or > 100) e.Add("Supply percentages must be 0–100 %.");
        if (s.Supply.TransitDaysByCountry.Values.Any(v => v is < 0 or > 365)) e.Add("Transit days must be 0–365.");
        if (s.Tc.DefaultKgPerTc <= 0) e.Add("Kg per TC must be positive.");
        if (string.IsNullOrWhiteSpace(s.General.Currency) || s.General.Currency.Length > 5) e.Add("Currency code is required (max 5 characters).");
        if (s.General.FiscalYearStartMonth is < 1 or > 12) e.Add("Fiscal year start month must be 1–12.");
        if (e.Count > 0) throw new ValidationException(e);
    }
}

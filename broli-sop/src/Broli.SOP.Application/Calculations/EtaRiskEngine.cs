using Broli.SOP.Domain.Enums;

namespace Broli.SOP.Application.Calculations;

public record EtaAssessment(EtaRiskLevel Level, string? Reason, int? DelayDays);

/// <summary>
/// Classifies an inbound supply line:
/// ETA after projected stockout → Critical; ETA after required date (or already passed) → Supply Risk;
/// ETA inside the safety window before the required/stockout date → Watch.
/// </summary>
public static class EtaRiskEngine
{
    public static EtaAssessment Assess(
        SupplyStatus status,
        DateOnly? eta,
        DateOnly? requiredDate,
        DateOnly? actualArrival,
        DateOnly? stockoutDate,
        DateOnly today,
        int watchWindowDays)
    {
        if (!status.IsOpen())
        {
            int? delivered = actualArrival is { } arr && requiredDate is { } req ? Math.Max(0, arr.DayNumber - req.DayNumber) : null;
            return new EtaAssessment(EtaRiskLevel.None, null, delivered);
        }

        if (eta is null)
            return new EtaAssessment(EtaRiskLevel.Watch, "No ETA communicated", null);

        var e = eta.Value;
        int? delay = requiredDate is { } r ? Math.Max(0, e.DayNumber - r.DayNumber) : null;

        if (stockoutDate is { } so && e > so)
            return new EtaAssessment(EtaRiskLevel.Critical,
                $"ETA {e:dd/MM} is {e.DayNumber - so.DayNumber} d after projected stockout {so:dd/MM}", delay);

        if (e < today)
            return new EtaAssessment(EtaRiskLevel.SupplyRisk,
                $"ETA {e:dd/MM} passed {today.DayNumber - e.DayNumber} d ago, not received", Math.Max(delay ?? 0, today.DayNumber - e.DayNumber));

        if (requiredDate is { } req2 && e > req2)
            return new EtaAssessment(EtaRiskLevel.SupplyRisk, $"ETA {delay} d after required date {req2:dd/MM}", delay);

        DateOnly? limit = (requiredDate, stockoutDate) switch
        {
            ({ } a, { } b) => a < b ? a : b,
            ({ } a, null) => a,
            (null, { } b) => b,
            _ => null,
        };
        if (limit is { } l && e > l.AddDays(-watchWindowDays))
            return new EtaAssessment(EtaRiskLevel.Watch, $"ETA within {watchWindowDays}-day safety window of {l:dd/MM}", delay);

        return new EtaAssessment(EtaRiskLevel.None, null, delay);
    }
}

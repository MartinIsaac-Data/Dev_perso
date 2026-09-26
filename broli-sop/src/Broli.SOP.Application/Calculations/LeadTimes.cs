namespace Broli.SOP.Application.Calculations;

/// <summary>Standard transit and lead times. Priority: supplier override › configured country override › country default.</summary>
public static class LeadTimes
{
    public static int? StandardTransitDays(int? supplierOverride, string? countryCode, int? countryDefault, SupplySettings settings)
    {
        if (supplierOverride is { } s) return s;
        if (countryCode is not null && settings.TransitDaysByCountry.TryGetValue(countryCode, out var c)) return c;
        return countryDefault;
    }

    /// <summary>Order-to-availability lead time of a purchased product (production + transit + port-to-warehouse).</summary>
    public static int? ProductLeadDays(ProductRef p, SupplySettings settings)
    {
        if (p.MainSupplierCode is null) return null;
        var transit = StandardTransitDays(p.SupplierTransitDays, p.SupplierCountryCode, p.CountryTransitDays, settings) ?? 0;
        var port = IsLocal(p.SupplierCountryCode) ? 0 : settings.PortToWarehouseDays;
        return (p.SupplierLeadDays ?? 0) + transit + port;
    }

    public static bool IsLocal(string? countryCode) => countryCode is null or "CM";

    /// <summary>Warehouse availability: ETA (or actual arrival) plus clearing time for goods that pass through a port.</summary>
    public static DateOnly? EstimatedDelivery(DateOnly? eta, DateOnly? actualArrival, string? port, SupplySettings settings)
    {
        var arrival = actualArrival ?? eta;
        if (arrival is null) return null;
        return port is null ? arrival : arrival.Value.AddDays(settings.PortToWarehouseDays);
    }
}

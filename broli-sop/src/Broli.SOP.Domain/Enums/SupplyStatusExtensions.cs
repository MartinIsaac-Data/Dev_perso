namespace Broli.SOP.Domain.Enums;

public static class SupplyStatusExtensions
{
    /// <summary>A line that is still expected to deliver stock.</summary>
    public static bool IsOpen(this SupplyStatus status) =>
        status is not (SupplyStatus.Delivered or SupplyStatus.Cancelled);

    /// <summary>Goods have physically left the supplier but are not yet in our warehouse.</summary>
    public static bool IsInTransit(this SupplyStatus status) =>
        status is SupplyStatus.Shipped or SupplyStatus.AtPort or SupplyStatus.Customs;

    /// <summary>Goods are at the destination port (including customs clearance).</summary>
    public static bool IsAtPort(this SupplyStatus status) =>
        status is SupplyStatus.AtPort or SupplyStatus.Customs;

    public static readonly SupplyStatus[] OpenStatuses =
        Enum.GetValues<SupplyStatus>().Where(s => s.IsOpen()).ToArray();

    public static readonly SupplyStatus[] TransitStatuses =
        Enum.GetValues<SupplyStatus>().Where(s => s.IsInTransit()).ToArray();

    public static readonly SupplyStatus[] PortStatuses =
        Enum.GetValues<SupplyStatus>().Where(s => s.IsAtPort()).ToArray();
}

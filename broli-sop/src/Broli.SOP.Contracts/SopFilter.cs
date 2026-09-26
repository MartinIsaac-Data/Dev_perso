using System.Text;

namespace Broli.SOP.Contracts;

/// <summary>
/// The global filter bar. Every analytical endpoint accepts it as query-string parameters,
/// so the same selection is applied consistently server-side.
/// Values are business keys (CArtSAP, supplier code, brand name…), never database ids.
/// </summary>
public class SopFilter
{
    public int? Year { get; set; }
    /// <summary>1–12. Empty = the latest month with data in <see cref="Year"/>.</summary>
    public List<int> Months { get; set; } = [];
    public List<string> Agencies { get; set; } = [];
    /// <summary>Product family (category code).</summary>
    public List<string> Categories { get; set; } = [];
    public List<string> Products { get; set; } = [];
    public List<string> Brands { get; set; } = [];
    public List<string> Suppliers { get; set; } = [];
    public List<string> Countries { get; set; } = [];
    public List<string> MaterialTypes { get; set; } = [];
    /// <summary>Supply status names (Shipped, AtPort…).</summary>
    public List<string> Statuses { get; set; } = [];

    public bool HasProductScope =>
        Categories.Count + Products.Count + Brands.Count + Suppliers.Count + Countries.Count + MaterialTypes.Count > 0;

    public int ActiveCount =>
        (Year.HasValue ? 1 : 0) + (Months.Count > 0 ? 1 : 0) + (Agencies.Count > 0 ? 1 : 0) + (Categories.Count > 0 ? 1 : 0)
        + (Products.Count > 0 ? 1 : 0) + (Brands.Count > 0 ? 1 : 0) + (Suppliers.Count > 0 ? 1 : 0)
        + (Countries.Count > 0 ? 1 : 0) + (MaterialTypes.Count > 0 ? 1 : 0) + (Statuses.Count > 0 ? 1 : 0);

    public SopFilter Clone() => new()
    {
        Year = Year,
        Months = [.. Months],
        Agencies = [.. Agencies],
        Categories = [.. Categories],
        Products = [.. Products],
        Brands = [.. Brands],
        Suppliers = [.. Suppliers],
        Countries = [.. Countries],
        MaterialTypes = [.. MaterialTypes],
        Statuses = [.. Statuses],
    };

    /// <summary>Serialises the filter as query-string pairs (without leading '?').</summary>
    public string ToQueryString()
    {
        var sb = new StringBuilder();
        void Add(string name, string value)
        {
            if (sb.Length > 0) sb.Append('&');
            sb.Append(name).Append('=').Append(Uri.EscapeDataString(value));
        }
        if (Year.HasValue) Add("year", Year.Value.ToString());
        foreach (var m in Months) Add("months", m.ToString());
        foreach (var v in Agencies) Add("agencies", v);
        foreach (var v in Categories) Add("categories", v);
        foreach (var v in Products) Add("products", v);
        foreach (var v in Brands) Add("brands", v);
        foreach (var v in Suppliers) Add("suppliers", v);
        foreach (var v in Countries) Add("countries", v);
        foreach (var v in MaterialTypes) Add("materialTypes", v);
        foreach (var v in Statuses) Add("statuses", v);
        return sb.ToString();
    }
}

/// <summary>Paging, sorting and free-text narrowing for server-side tables.</summary>
public class TableQuery
{
    public const int MaxPageSize = 500;

    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 25;
    public string? Sort { get; set; }
    public bool Desc { get; set; }
    public string? Search { get; set; }
    /// <summary>Page-specific narrowing, e.g. a coverage status or risk level coming from a KPI drill-down.</summary>
    public string? View { get; set; }

    public int SafePage => Math.Max(1, Page);
    public int SafePageSize => Math.Clamp(PageSize, 1, MaxPageSize);

    public string ToQueryString()
    {
        var parts = new List<string> { $"page={SafePage}", $"pageSize={SafePageSize}" };
        if (!string.IsNullOrWhiteSpace(Sort)) parts.Add($"sort={Uri.EscapeDataString(Sort)}&desc={Desc.ToString().ToLowerInvariant()}");
        if (!string.IsNullOrWhiteSpace(Search)) parts.Add($"search={Uri.EscapeDataString(Search)}");
        if (!string.IsNullOrWhiteSpace(View)) parts.Add($"view={Uri.EscapeDataString(View)}");
        return string.Join('&', parts);
    }
}

public record PagedResult<T>(IReadOnlyList<T> Items, int Total, int Page, int PageSize)
{
    public int PageCount => PageSize <= 0 ? 0 : (int)Math.Ceiling(Total / (double)PageSize);
}

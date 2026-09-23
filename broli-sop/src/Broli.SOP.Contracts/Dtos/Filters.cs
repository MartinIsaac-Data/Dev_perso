namespace Broli.SOP.Contracts.Dtos;

public record FilterOptions(
    IReadOnlyList<int> Years,
    int? DefaultYear,
    int? DefaultMonth,
    IReadOnlyList<Option> Agencies,
    IReadOnlyList<Option> Categories,
    IReadOnlyList<Option> Brands,
    IReadOnlyList<Option> Suppliers,
    IReadOnlyList<Option> Countries,
    IReadOnlyList<Option> MaterialTypes,
    IReadOnlyList<Option> Statuses);

public record SearchResult(string Type, string Key, string Title, string? Subtitle, string Url);

public record DataStatus(
    bool HasDemoData,
    bool HasRealData,
    DateOnly? LatestStockMonth,
    DateTime? LastImportUtc,
    IReadOnlyDictionary<string, int> RowCounts);

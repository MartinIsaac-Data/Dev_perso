using Microsoft.Extensions.Caching.Memory;

namespace Broli.SOP.Application.Services;

/// <summary>Filter options, global search and data status.</summary>
public sealed class ReferenceService(ISopReadRepository repo, IMemoryCache cache, IDataVersion version)
{
    public async Task<FilterOptions> GetFilterOptionsAsync(CancellationToken ct) =>
        (await cache.GetOrCreateAsync($"filter-options:{version.Current}", e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(10);
            e.Size = 1;
            return repo.GetFilterOptionsAsync(ct);
        }))!;

    public Task<IReadOnlyList<SearchResult>> SearchAsync(string? term, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(term) || term.Trim().Length < 2) return Task.FromResult<IReadOnlyList<SearchResult>>([]);
        return repo.SearchAsync(term.Trim(), 20, ct);
    }

    public Task<DataStatus> GetDataStatusAsync(CancellationToken ct) => repo.GetDataStatusAsync(ct);
}

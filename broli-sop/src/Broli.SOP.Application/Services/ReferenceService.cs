using Microsoft.Extensions.Caching.Memory;

namespace Broli.SOP.Application.Services;

/// <summary>Filter options, global search and data status.</summary>
public sealed class ReferenceService(ISopReadRepository repo, IMemoryCache cache, IDataVersion version, ICurrentUser user)
{
    public async Task<FilterOptions> GetFilterOptionsAsync(CancellationToken ct)
    {
        var all = (await cache.GetOrCreateAsync($"filter-options:{version.Current}", e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(10);
            e.Size = 1;
            return repo.GetFilterOptionsAsync(ct);
        }))!;
        if (user.ScopeAgencies.Count == 0 && user.ScopeCategories.Count == 0) return all;
        bool In(IReadOnlyList<string> scope, string v) => scope.Count == 0 || scope.Contains(v, StringComparer.OrdinalIgnoreCase);
        return all with
        {
            Agencies = all.Agencies.Where(o => In(user.ScopeAgencies, o.Value)).ToList(),
            Categories = all.Categories.Where(o => In(user.ScopeCategories, o.Value)).ToList(),
        };
    }

    public async Task<IReadOnlyList<SearchResult>> SearchAsync(string? term, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(term) || term.Trim().Length < 2) return [];
        return await repo.SearchAsync(term.Trim(), 20, user.ScopeCategories, ct);
    }

    public Task<DataStatus> GetDataStatusAsync(CancellationToken ct) => repo.GetDataStatusAsync(ct);
}

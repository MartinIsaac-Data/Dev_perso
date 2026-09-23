namespace Broli.SOP.Application.Analytics;

/// <summary>
/// Row-level security: restricts a filter to the agencies and product families a user may see.
/// Applied centrally by the analytics engine, so every dashboard, export and drill-down inherits it.
/// </summary>
public static class DataScope
{
    /// <summary>Value that matches nothing: used when the user's selection lies entirely outside the scope.</summary>
    public const string NoAccess = "__no_access__";

    public static SopFilter Apply(SopFilter filter, ICurrentUser user)
    {
        if (user.ScopeAgencies.Count == 0 && user.ScopeCategories.Count == 0) return filter;
        var f = filter.Clone();
        f.Agencies = Restrict(f.Agencies, user.ScopeAgencies);
        f.Categories = Restrict(f.Categories, user.ScopeCategories);
        return f;
    }

    public static List<string> Restrict(List<string> requested, IReadOnlyList<string> allowed)
    {
        if (allowed.Count == 0) return requested;
        if (requested.Count == 0) return [.. allowed];
        var kept = requested.Where(r => allowed.Contains(r, StringComparer.OrdinalIgnoreCase)).ToList();
        return kept.Count > 0 ? kept : [NoAccess];
    }

    public static bool AllowsCategory(ICurrentUser user, string? categoryCode) =>
        user.ScopeCategories.Count == 0 || (categoryCode is not null && user.ScopeCategories.Contains(categoryCode, StringComparer.OrdinalIgnoreCase));
}

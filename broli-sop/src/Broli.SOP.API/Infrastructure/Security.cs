using System.Security.Claims;
using Broli.SOP.Application.Abstractions;
using Broli.SOP.Infrastructure;
using Microsoft.AspNetCore.Authorization;

namespace Broli.SOP.API.Infrastructure;

/// <summary>The caller as seen from the JWT: username plus the permission claims issued at login.</summary>
public sealed class HttpCurrentUser(IHttpContextAccessor accessor) : ICurrentUser
{
    private ClaimsPrincipal? Principal => SystemActor.Name is null ? accessor.HttpContext?.User : null;

    public string Username => SystemActor.Name ?? Principal?.Identity?.Name ?? "anonymous";
    public bool IsAuthenticated => SystemActor.Name is not null || Principal?.Identity?.IsAuthenticated == true;
    public bool Has(string permission) => SystemActor.Name is not null || Principal?.HasClaim(JwtTokenService.PermissionClaim, permission) == true;
    public IReadOnlyList<string> ScopeAgencies => Claims(JwtTokenService.ScopeAgencyClaim);
    public IReadOnlyList<string> ScopeCategories => Claims(JwtTokenService.ScopeCategoryClaim);

    private IReadOnlyList<string> Claims(string type) => Principal?.FindAll(type).Select(c => c.Value).ToList() ?? [];
}

public static class AuthorizationSetup
{
    /// <summary>One policy per permission code, so controllers write [Authorize(Policy = Permissions.X)].</summary>
    public static void AddPermissionPolicies(this AuthorizationOptions options)
    {
        foreach (var (code, _) in Contracts.Security.Permissions.All)
            options.AddPolicy(code, p => p.RequireAuthenticatedUser().RequireClaim(JwtTokenService.PermissionClaim, code));
        options.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build();
    }
}

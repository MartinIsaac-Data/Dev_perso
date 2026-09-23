using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Broli.SOP.Application.Abstractions;
using Broli.SOP.Domain.Entities;
using Microsoft.AspNetCore.Identity;
using Microsoft.IdentityModel.Tokens;

namespace Broli.SOP.Infrastructure;

/// <summary>PBKDF2 (HMAC-SHA512, 100k iterations, random salt) via ASP.NET Core Identity's hasher.</summary>
public sealed class PasswordHasher : IPasswordHasher
{
    private readonly PasswordHasher<AppUser> _inner = new();

    public string Hash(string password) => _inner.HashPassword(null!, password);

    public bool Verify(string hash, string password)
    {
        if (string.IsNullOrEmpty(hash)) return false;
        try
        {
            return _inner.VerifyHashedPassword(null!, hash, password) != PasswordVerificationResult.Failed;
        }
        catch (FormatException)
        {
            return false;
        }
    }
}

public sealed class JwtOptions
{
    public const string Section = "Jwt";
    public string Issuer { get; set; } = "Broli.SOP";
    public string Audience { get; set; } = "Broli.SOP";
    /// <summary>HMAC signing key, at least 32 characters. Provide via configuration / environment, never in code.</summary>
    public string Key { get; set; } = "";
    public int LifetimeMinutes { get; set; } = 600;
}

public sealed class JwtTokenService(JwtOptions options, IClock clock) : ITokenService
{
    public const string PermissionClaim = "perm";
    public const string ScopeAgencyClaim = "scope_agency";
    public const string ScopeCategoryClaim = "scope_category";

    public IssuedToken Issue(string username, string displayName, IReadOnlyCollection<string> roles, IReadOnlyCollection<string> permissions,
        IReadOnlyCollection<string>? scopeAgencies = null, IReadOnlyCollection<string>? scopeCategories = null)
    {
        var now = clock.UtcNow;
        var expires = now.AddMinutes(options.LifetimeMinutes);
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, username),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString("N")),
            new(ClaimTypes.Name, username),
            new("name_display", displayName),
        };
        claims.AddRange(roles.Select(r => new Claim(ClaimTypes.Role, r)));
        claims.AddRange(permissions.Select(p => new Claim(PermissionClaim, p)));
        claims.AddRange((scopeAgencies ?? []).Select(a => new Claim(ScopeAgencyClaim, a)));
        claims.AddRange((scopeCategories ?? []).Select(c => new Claim(ScopeCategoryClaim, c)));

        var credentials = new SigningCredentials(new SymmetricSecurityKey(Encoding.UTF8.GetBytes(options.Key)), SecurityAlgorithms.HmacSha256);
        var token = new JwtSecurityToken(options.Issuer, options.Audience, claims, now, expires, credentials);
        return new IssuedToken(new JwtSecurityTokenHandler().WriteToken(token), expires);
    }
}

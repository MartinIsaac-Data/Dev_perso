using Microsoft.Extensions.Logging;

namespace Broli.SOP.Application.Services;

/// <summary>
/// Username/password authentication with lockout. The token format and the credential store
/// sit behind interfaces so Microsoft Entra ID / Active Directory can replace them later.
/// </summary>
public sealed class AuthService(
    IUserRepository users,
    IPasswordHasher hasher,
    ITokenService tokens,
    IAuditLogger audit,
    IClock clock,
    ILogger<AuthService> logger)
{
    public const int MaxFailedAttempts = 5;
    public static readonly TimeSpan LockoutDuration = TimeSpan.FromMinutes(15);
    public const int MinPasswordLength = 10;

    public async Task<LoginResponse?> LoginAsync(LoginRequest request, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(request.Username) || string.IsNullOrEmpty(request.Password)) return null;
        var user = await users.FindByUsernameAsync(request.Username.Trim(), ct);
        var now = clock.UtcNow;

        if (user is null || !user.IsActive)
        {
            logger.LogWarning("Failed login for unknown or inactive user {Username}", request.Username);
            return null;
        }
        if (user.LockoutEndUtc is { } until && until > now)
        {
            logger.LogWarning("Login attempt for locked-out user {Username}", user.Username);
            return null;
        }
        if (!hasher.Verify(user.PasswordHash, request.Password))
        {
            user.FailedLoginCount++;
            if (user.FailedLoginCount >= MaxFailedAttempts)
            {
                user.LockoutEndUtc = now.Add(LockoutDuration);
                user.FailedLoginCount = 0;
                await audit.LogAsync("Account locked", "Security", user.Username, null, $"until {user.LockoutEndUtc:u}", ct);
            }
            await users.SaveChangesAsync(ct);
            logger.LogWarning("Failed login for {Username}", user.Username);
            return null;
        }

        user.FailedLoginCount = 0;
        user.LockoutEndUtc = null;
        user.LastLoginUtc = now;
        await users.SaveChangesAsync(ct);

        var info = await GetUserInfoAsync(user, ct);
        var token = tokens.Issue(user.Username, user.DisplayName, info.Roles, info.Permissions);
        await audit.LogAsync("Login", "Security", user.Username, null, null, ct);
        return new LoginResponse(token.Token, token.ExpiresAtUtc, info);
    }

    public async Task<UserInfo?> GetUserInfoAsync(string username, CancellationToken ct)
    {
        var user = await users.FindByUsernameAsync(username, ct);
        return user is null || !user.IsActive ? null : await GetUserInfoAsync(user, ct);
    }

    private async Task<UserInfo> GetUserInfoAsync(AppUser user, CancellationToken ct)
    {
        var permissions = await users.GetPermissionsAsync(user.Id, ct);
        var roles = user.Roles.Select(r => r.Role?.Name).OfType<string>().Order().ToList();
        return new UserInfo(user.Username, user.DisplayName, user.Department, roles, permissions);
    }

    public async Task ChangePasswordAsync(string username, ChangePasswordRequest request, CancellationToken ct)
    {
        var user = await users.FindByUsernameAsync(username, ct) ?? throw new ValidationException(["Unknown user."]);
        if (!hasher.Verify(user.PasswordHash, request.CurrentPassword)) throw new ValidationException(["Current password is incorrect."]);
        ValidatePassword(request.NewPassword);
        user.PasswordHash = hasher.Hash(request.NewPassword);
        await users.SaveChangesAsync(ct);
        await audit.LogAsync("Changed password", "Security", user.Username, null, null, ct);
    }

    public static void ValidatePassword(string? password)
    {
        var errors = new List<string>();
        if (string.IsNullOrEmpty(password) || password.Length < MinPasswordLength)
            errors.Add($"Password must be at least {MinPasswordLength} characters.");
        else if (!password.Any(char.IsLetter) || !password.Any(char.IsDigit))
            errors.Add("Password must contain letters and digits.");
        if (errors.Count > 0) throw new ValidationException(errors);
    }
}

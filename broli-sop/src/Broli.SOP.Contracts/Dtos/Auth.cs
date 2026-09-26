namespace Broli.SOP.Contracts.Dtos;

public record LoginRequest(string Username, string Password);

public record UserInfo(
    string Username,
    string DisplayName,
    string? Department,
    IReadOnlyList<string> Roles,
    IReadOnlyList<string> Permissions,
    IReadOnlyList<string>? ScopeAgencies = null,
    IReadOnlyList<string>? ScopeCategories = null);

public record LoginResponse(string Token, DateTime ExpiresAtUtc, UserInfo User);

public record ChangePasswordRequest(string CurrentPassword, string NewPassword);

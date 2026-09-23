using Broli.SOP.Contracts.Settings;

namespace Broli.SOP.Contracts.Dtos;

public record UserDto(
    int Id,
    string Username,
    string DisplayName,
    string? Email,
    string? Department,
    bool IsActive,
    bool IsDemo,
    IReadOnlyList<string> Roles,
    DateTime? LastLoginUtc,
    bool IsLockedOut,
    IReadOnlyList<string> ScopeAgencies,
    IReadOnlyList<string> ScopeCategories);

public record UserUpsert(
    string Username,
    string DisplayName,
    string? Email,
    string? Department,
    bool IsActive,
    IReadOnlyList<string> Roles,
    string? Password,
    IReadOnlyList<string>? ScopeAgencies = null,
    IReadOnlyList<string>? ScopeCategories = null);

public record PermissionDto(string Code, string Description);

public record RoleDto(int Id, string Name, string Description, bool IsSystem, IReadOnlyList<string> Permissions, int UserCount);

public record RoleUpsert(string Name, string Description, IReadOnlyList<string> Permissions);

public record AuditEntryDto(
    long Id,
    DateTime TimestampUtc,
    string Username,
    string Action,
    string Module,
    string? ObjectRef,
    string? OldValue,
    string? NewValue);

public record SettingsDto(
    CoverageSettings Coverage,
    SafetyStockSettings SafetyStock,
    ForecastSettings Forecast,
    SupplySettings Supply,
    TcSettings Tc,
    GeneralSettings General,
    AlertSettings? Alerts = null);

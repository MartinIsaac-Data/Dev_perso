using Broli.SOP.Contracts.Security;

namespace Broli.SOP.Application.Services;

public sealed class AdminService(
    IUserRepository users,
    IAuditRepository auditRepo,
    IPasswordHasher hasher,
    IAuditLogger audit,
    IClock clock)
{
    public async Task<IReadOnlyList<UserDto>> ListUsersAsync(CancellationToken ct) =>
        (await users.ListAsync(ct)).Select(ToDto).OrderBy(u => u.Username).ToList();

    public async Task<UserDto> CreateUserAsync(UserUpsert request, CancellationToken ct)
    {
        Validate(request, isNew: true);
        if (await users.FindByUsernameAsync(request.Username.Trim(), ct) is not null)
            throw new ValidationException([$"User '{request.Username}' already exists."]);
        AuthService.ValidatePassword(request.Password);

        var user = new AppUser
        {
            Username = request.Username.Trim(),
            PasswordHash = hasher.Hash(request.Password!),
            CreatedAtUtc = clock.UtcNow,
        };
        await ApplyAsync(user, request, ct);
        users.Add(user);
        await users.SaveChangesAsync(ct);
        await audit.LogAsync("Created user", "Administration", user.Username, null, Describe(user), ct);
        return ToDto(user);
    }

    public async Task<UserDto?> UpdateUserAsync(int id, UserUpsert request, string actingUser, CancellationToken ct)
    {
        Validate(request, isNew: false);
        var user = await users.FindAsync(id, ct);
        if (user is null) return null;
        if (string.Equals(user.Username, actingUser, StringComparison.OrdinalIgnoreCase)
            && (!request.IsActive || !request.Roles.Contains("ADMIN", StringComparer.OrdinalIgnoreCase))
            && user.Roles.Any(r => r.Role?.Name == "ADMIN"))
            throw new ValidationException(["You cannot deactivate yourself or remove your own ADMIN role."]);

        var before = Describe(user);
        await ApplyAsync(user, request, ct);
        if (!string.IsNullOrEmpty(request.Password))
        {
            AuthService.ValidatePassword(request.Password);
            user.PasswordHash = hasher.Hash(request.Password);
            user.LockoutEndUtc = null;
            user.FailedLoginCount = 0;
            await audit.LogAsync("Reset password", "Administration", user.Username, null, null, ct);
        }
        await users.SaveChangesAsync(ct);
        var after = Describe(user);
        if (before != after) await audit.LogAsync("Updated user", "Administration", user.Username, before, after, ct);
        return ToDto(user);
    }

    private async Task ApplyAsync(AppUser user, UserUpsert r, CancellationToken ct)
    {
        var roles = await users.FindRolesAsync(r.Roles, ct);
        var unknown = r.Roles.Except(roles.Select(x => x.Name), StringComparer.OrdinalIgnoreCase).ToList();
        if (unknown.Count > 0) throw new ValidationException([$"Unknown role(s): {string.Join(", ", unknown)}."]);

        user.DisplayName = r.DisplayName.Trim();
        user.Email = string.IsNullOrWhiteSpace(r.Email) ? null : r.Email.Trim();
        user.Department = string.IsNullOrWhiteSpace(r.Department) ? null : r.Department.Trim();
        user.IsActive = r.IsActive;
        user.ScopeAgencies = AuthService.Join(r.ScopeAgencies);
        user.ScopeCategories = AuthService.Join(r.ScopeCategories);
        user.Roles.RemoveAll(ur => !roles.Any(x => x.Id == ur.RoleId));
        foreach (var role in roles.Where(x => user.Roles.All(ur => ur.RoleId != x.Id)))
            user.Roles.Add(new UserRole { User = user, RoleId = role.Id, Role = role });
    }

    private static void Validate(UserUpsert r, bool isNew)
    {
        var errors = new List<string>();
        if (isNew && (string.IsNullOrWhiteSpace(r.Username) || r.Username.Trim().Length < 3 || !r.Username.Trim().All(c => char.IsLetterOrDigit(c) || c is '.' or '_' or '-')))
            errors.Add("Username must be at least 3 characters (letters, digits, . _ -).");
        if (string.IsNullOrWhiteSpace(r.DisplayName)) errors.Add("Display name is required.");
        if (r.Roles.Count == 0) errors.Add("At least one role is required.");
        if (errors.Count > 0) throw new ValidationException(errors);
    }

    public async Task<IReadOnlyList<RoleDto>> ListRolesAsync(CancellationToken ct)
    {
        var all = await users.ListAsync(ct);
        return (await users.ListRolesAsync(ct))
            .Select(r => new RoleDto(r.Id, r.Name, r.Description, r.IsSystem, r.Permissions.Select(p => p.Permission).Order().ToList(),
                all.Count(u => u.Roles.Any(ur => ur.RoleId == r.Id))))
            .OrderBy(r => r.Name)
            .ToList();
    }

    public IReadOnlyList<PermissionDto> ListPermissions() =>
        Permissions.All.Select(p => new PermissionDto(p.Code, p.Description)).ToList();

    public async Task<RoleDto> CreateRoleAsync(RoleUpsert request, CancellationToken ct)
    {
        var name = (request.Name ?? "").Trim().ToUpperInvariant();
        if (name.Length < 2) throw new ValidationException(["Role name is required."]);
        if ((await users.FindRolesAsync([name], ct)).Count > 0) throw new ValidationException([$"Role '{name}' already exists."]);
        var role = new AppRole { Name = name, Description = request.Description?.Trim() ?? "" };
        SetPermissions(role, request.Permissions);
        users.AddRole(role);
        await users.SaveChangesAsync(ct);
        await audit.LogAsync("Created role", "Administration", role.Name, null, string.Join(", ", request.Permissions), ct);
        return new RoleDto(role.Id, role.Name, role.Description, role.IsSystem, role.Permissions.Select(p => p.Permission).ToList(), 0);
    }

    public async Task<bool> UpdateRoleAsync(int id, RoleUpsert request, CancellationToken ct)
    {
        var role = await users.FindRoleAsync(id, ct);
        if (role is null) return false;
        if (role.Name == "ADMIN" && !request.Permissions.Contains(Permissions.UsersManage))
            throw new ValidationException(["The ADMIN role must keep the users.manage permission."]);
        var before = string.Join(", ", role.Permissions.Select(p => p.Permission).Order());
        role.Description = request.Description?.Trim() ?? role.Description;
        SetPermissions(role, request.Permissions);
        await users.SaveChangesAsync(ct);
        var after = string.Join(", ", role.Permissions.Select(p => p.Permission).Order());
        await audit.LogAsync("Updated role permissions", "Administration", role.Name, before, after, ct);
        return true;
    }

    public async Task<bool> DeleteRoleAsync(int id, CancellationToken ct)
    {
        var role = await users.FindRoleAsync(id, ct);
        if (role is null) return false;
        if (role.IsSystem) throw new ValidationException(["System roles cannot be deleted."]);
        if ((await users.ListAsync(ct)).Any(u => u.Roles.Any(r => r.RoleId == id)))
            throw new ValidationException(["The role is still assigned to users."]);
        users.RemoveRole(role);
        await users.SaveChangesAsync(ct);
        await audit.LogAsync("Deleted role", "Administration", role.Name, null, null, ct);
        return true;
    }

    private static void SetPermissions(AppRole role, IEnumerable<string> permissions)
    {
        var valid = Permissions.All.Select(p => p.Code).ToHashSet();
        var requested = permissions.Distinct().ToList();
        var unknown = requested.Where(p => !valid.Contains(p)).ToList();
        if (unknown.Count > 0) throw new ValidationException([$"Unknown permission(s): {string.Join(", ", unknown)}."]);
        role.Permissions.RemoveAll(p => !requested.Contains(p.Permission));
        foreach (var p in requested.Where(p => role.Permissions.All(x => x.Permission != p)))
            role.Permissions.Add(new RolePermission { Role = role, Permission = p });
    }

    public async Task<PagedResult<AuditEntryDto>> GetAuditAsync(string? search, string? module, int page, int pageSize, CancellationToken ct)
    {
        var result = await auditRepo.QueryAsync(search, module, Math.Max(1, page), Math.Clamp(pageSize, 1, 200), ct);
        return new PagedResult<AuditEntryDto>(
            result.Items.Select(a => new AuditEntryDto(a.Id, a.TimestampUtc, a.Username, a.Action, a.Module, a.ObjectRef, a.OldValue, a.NewValue)).ToList(),
            result.Total, result.Page, result.PageSize);
    }

    private UserDto ToDto(AppUser u) => new(u.Id, u.Username, u.DisplayName, u.Email, u.Department, u.IsActive, u.IsDemo,
        u.Roles.Select(r => r.Role?.Name).OfType<string>().Order().ToList(), u.LastLoginUtc, u.LockoutEndUtc is { } l && l > clock.UtcNow,
        AuthService.Split(u.ScopeAgencies), AuthService.Split(u.ScopeCategories));

    private static string Describe(AppUser u) =>
        $"{u.DisplayName} | {u.Department} | {(u.IsActive ? "active" : "inactive")} | roles: {string.Join(", ", u.Roles.Select(r => r.Role?.Name).Order())}"
        + $" | scope: agencies [{u.ScopeAgencies ?? "all"}], families [{u.ScopeCategories ?? "all"}]";
}

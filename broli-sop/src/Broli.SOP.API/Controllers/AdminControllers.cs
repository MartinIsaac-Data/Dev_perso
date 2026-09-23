using Broli.SOP.Application.Import;
using Broli.SOP.Application.Services;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace Broli.SOP.API.Controllers;

[ApiController]
[Route("api/auth")]
public sealed class AuthController(AuthService auth) : ControllerBase
{
    [HttpPost("login")]
    [AllowAnonymous]
    [EnableRateLimiting("login")]
    public async Task<ActionResult<LoginResponse>> Login(LoginRequest request, CancellationToken ct) =>
        await auth.LoginAsync(request, ct) is { } response
            ? response
            : Unauthorized(new ApiError("Invalid username or password, or the account is locked."));

    [HttpGet("me")]
    public async Task<ActionResult<UserInfo>> Me(CancellationToken ct) =>
        await auth.GetUserInfoAsync(User.Identity!.Name!, ct) is { } info ? info : Unauthorized();

    [HttpPost("change-password")]
    public async Task<IActionResult> ChangePassword(ChangePasswordRequest request, CancellationToken ct)
    {
        await auth.ChangePasswordAsync(User.Identity!.Name!, request, ct);
        return NoContent();
    }
}

[ApiController]
[Route("api/imports")]
[Authorize(Policy = Permissions.DataImport)]
public sealed class ImportsController(ImportService imports) : ControllerBase
{
    public const long MaxFileBytes = 25 * 1024 * 1024;

    [HttpGet("templates")]
    public IReadOnlyList<ImportTemplateInfo> Templates() => imports.GetTemplates();

    [HttpGet("templates/{type}")]
    public IActionResult Template(string type) =>
        imports.GetTemplateFile(type) is { } t
            ? File(t.Content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", t.FileName)
            : NotFound(new ApiError($"Unknown template '{type}'."));

    [HttpPost("preview/{type}")]
    [RequestSizeLimit(MaxFileBytes)]
    public async Task<ActionResult<ImportPreview>> Preview(string type, IFormFile file, CancellationToken ct)
    {
        if (file.Length == 0) return BadRequest(new ApiError("The file is empty."));
        if (!file.FileName.EndsWith(".xlsx", StringComparison.OrdinalIgnoreCase))
            return BadRequest(new ApiError("Only .xlsx files are accepted. Save the workbook as Excel Workbook (.xlsx)."));
        await using var buffer = new MemoryStream();
        await file.CopyToAsync(buffer, ct);
        buffer.Position = 0;
        return await imports.PreviewAsync(type, Path.GetFileName(file.FileName), buffer, User.Identity!.Name!, ct);
    }

    [HttpPost("{id:guid}/commit")]
    public Task<ImportResult> Commit(Guid id, CancellationToken ct) => imports.CommitAsync(id, User.Identity!.Name!, ct);

    [HttpGet("history")]
    public Task<IReadOnlyList<ImportBatchDto>> History(CancellationToken ct) => imports.GetHistoryAsync(ct);

    [HttpPost("purge-demo")]
    public async Task<IActionResult> PurgeDemo(CancellationToken ct) => Ok(new { removed = await imports.PurgeDemoAsync(ct) });
}

[ApiController]
[Route("api/settings")]
public sealed class SettingsController(SettingsService settings) : ControllerBase
{
    [HttpGet]
    public Task<SettingsDto> Get(CancellationToken ct) => settings.GetAsync(ct);

    [HttpPut]
    [Authorize(Policy = Permissions.ConfigEdit)]
    public async Task<IActionResult> Save(SettingsDto dto, CancellationToken ct)
    {
        await settings.SaveAsync(dto, ct);
        return NoContent();
    }
}

[ApiController]
[Route("api/admin")]
public sealed class AdminController(AdminService admin) : ControllerBase
{
    [HttpGet("users")]
    [Authorize(Policy = Permissions.UsersManage)]
    public Task<IReadOnlyList<UserDto>> Users(CancellationToken ct) => admin.ListUsersAsync(ct);

    [HttpPost("users")]
    [Authorize(Policy = Permissions.UsersManage)]
    public Task<UserDto> CreateUser(UserUpsert request, CancellationToken ct) => admin.CreateUserAsync(request, ct);

    [HttpPut("users/{id:int}")]
    [Authorize(Policy = Permissions.UsersManage)]
    public async Task<ActionResult<UserDto>> UpdateUser(int id, UserUpsert request, CancellationToken ct) =>
        await admin.UpdateUserAsync(id, request, User.Identity!.Name!, ct) is { } u ? u : NotFound();

    [HttpGet("roles")]
    [Authorize(Policy = Permissions.UsersManage)]
    public Task<IReadOnlyList<RoleDto>> Roles(CancellationToken ct) => admin.ListRolesAsync(ct);

    [HttpGet("permissions")]
    [Authorize(Policy = Permissions.UsersManage)]
    public IReadOnlyList<PermissionDto> PermissionList() => admin.ListPermissions();

    [HttpPost("roles")]
    [Authorize(Policy = Permissions.UsersManage)]
    public Task<RoleDto> CreateRole(RoleUpsert request, CancellationToken ct) => admin.CreateRoleAsync(request, ct);

    [HttpPut("roles/{id:int}")]
    [Authorize(Policy = Permissions.UsersManage)]
    public async Task<IActionResult> UpdateRole(int id, RoleUpsert request, CancellationToken ct) =>
        await admin.UpdateRoleAsync(id, request, ct) ? NoContent() : NotFound();

    [HttpDelete("roles/{id:int}")]
    [Authorize(Policy = Permissions.UsersManage)]
    public async Task<IActionResult> DeleteRole(int id, CancellationToken ct) =>
        await admin.DeleteRoleAsync(id, ct) ? NoContent() : NotFound();

    [HttpGet("audit")]
    [Authorize(Policy = Permissions.AuditView)]
    public Task<PagedResult<AuditEntryDto>> Audit([FromQuery] string? search, [FromQuery] string? module,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 50, CancellationToken ct = default) =>
        admin.GetAuditAsync(search, module, page, pageSize, ct);
}

using Broli.SOP.API.Infrastructure;
using Broli.SOP.Application.Reporting;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Broli.SOP.API.Controllers;

/// <summary>Weekly follow-up of the reports owed to the S&amp;OP process. Reading: S&amp;OP users; import: data administrators.</summary>
[ApiController]
[Route("api/reporting")]
[Authorize(Policy = Permissions.ActionsView)]
public sealed class ReportingController(ReportingService service) : ControllerBase
{
    [HttpGet]
    public Task<ReportingDashboard> Get([FromQuery] string? week, CancellationToken ct) => service.GetDashboardAsync(week, ct);

    /// <summary>Reminds the owner(s) of one report, or of every late / missing report of the week when <c>code</c> is empty.</summary>
    [HttpPost("remind")]
    [Authorize(Policy = Permissions.ActionsEdit)]
    public Task<ReportingReminderResult> Remind(ReportingReminderRequest request, CancellationToken ct) => service.RemindAsync(request, ct);

    [HttpPost("import/preview")]
    [Authorize(Policy = Permissions.DataImport)]
    [RequestSizeLimit(ImportsController.MaxFileBytes)]
    public async Task<ActionResult<ReportingImportPreview>> Preview(IFormFile file, CancellationToken ct)
    {
        if (file.Length == 0) return BadRequest(new ApiError("Le fichier est vide."));
        if (!file.FileName.EndsWith(".xlsx", StringComparison.OrdinalIgnoreCase))
            return BadRequest(new ApiError("Seuls les fichiers .xlsx sont acceptés. Enregistrez le classeur au format Classeur Excel (.xlsx)."));
        await using var buffer = new MemoryStream();
        await file.CopyToAsync(buffer, ct);
        buffer.Position = 0;
        return await service.PreviewAsync(Path.GetFileName(file.FileName), buffer, User.Identity!.Name!, ct);
    }

    [HttpPost("import/{id:guid}/commit")]
    [Authorize(Policy = Permissions.DataImport)]
    public Task<ReportingImportResult> Commit(Guid id, CancellationToken ct) => service.CommitAsync(id, User.Identity!.Name!, ct);
}

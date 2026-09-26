using Broli.SOP.API.Infrastructure;
using Broli.SOP.Application.Import;
using Broli.SOP.Application.Services;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Broli.SOP.API.Controllers;

[ApiController]
[Route("api/actions")]
[Authorize(Policy = Permissions.ActionsView)]
public sealed class ActionsController(ActionService service) : ControllerBase
{
    [HttpGet]
    public Task<PagedResult<ActionDto>> List([FromQuery] ActionQuery query, CancellationToken ct) => service.ListAsync(query, ct);

    [HttpGet("summary")]
    public Task<ActionSummary> Summary(CancellationToken ct) => service.SummaryAsync(ct);

    [HttpPost]
    [Authorize(Policy = Permissions.ActionsEdit)]
    public Task<ActionDto> Create(ActionUpsert request, CancellationToken ct) => service.CreateAsync(request, ct);

    [HttpPut("{id:int}")]
    [Authorize(Policy = Permissions.ActionsEdit)]
    public async Task<ActionResult<ActionDto>> Update(int id, ActionUpsert request, CancellationToken ct) =>
        await service.UpdateAsync(id, request, ct) is { } dto ? dto : NotFound();
}

[ApiController]
[Route("api/meeting")]
[Authorize(Policy = Permissions.ActionsView)]
public sealed class MeetingController(MeetingService service) : ControllerBase
{
    [HttpGet]
    public Task<MeetingView> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetAsync(filter, ct);
}

/// <summary>Every signed-in user reads and acknowledges their own notifications.</summary>
[ApiController]
[Route("api/notifications")]
public sealed class NotificationsController(NotificationService service) : ControllerBase
{
    [HttpGet]
    public Task<NotificationFeed> Feed(CancellationToken ct) => service.FeedAsync(ct);

    [HttpPost("{id:long}/read")]
    public async Task<IActionResult> Read(long id, CancellationToken ct) { await service.MarkReadAsync(id, ct); return NoContent(); }

    [HttpPost("read-all")]
    public async Task<IActionResult> ReadAll(CancellationToken ct) { await service.MarkReadAsync(null, ct); return NoContent(); }
}

[ApiController]
[Route("api/alerts")]
[Authorize(Policy = Permissions.ConfigEdit)]
public sealed class AlertsController(AlertEngine alerts) : ControllerBase
{
    /// <summary>Evaluates the alert rules now (they also run after every automated refresh and daily).</summary>
    [HttpPost("run")]
    public Task<AlertRunResult> Run(CancellationToken ct) => alerts.RunAsync(ct);
}

[ApiController]
[Route("api/data-sources")]
[Authorize(Policy = Permissions.DataImport)]
public sealed class DataSourcesController(DataSourceService sources, DataRefreshService refresh, RefreshScheduler scheduler) : ControllerBase
{
    [HttpGet]
    public Task<IReadOnlyList<DataSourceDto>> List(CancellationToken ct) => sources.ListAsync(ct);

    [HttpGet("info")]
    public RefreshInfo Info() => refresh.Info(scheduler.Enabled, scheduler.LastRun);

    [HttpPost]
    public Task<DataSourceDto> Create(DataSourceUpsert request, CancellationToken ct) => sources.CreateAsync(request, ct);

    [HttpPut("{id:int}")]
    public async Task<ActionResult<DataSourceDto>> Update(int id, DataSourceUpsert request, CancellationToken ct) =>
        await sources.UpdateAsync(id, request, ct) is { } dto ? dto : NotFound();

    [HttpDelete("{id:int}")]
    public async Task<IActionResult> Delete(int id, CancellationToken ct) => await sources.DeleteAsync(id, ct) ? NoContent() : NotFound();

    [HttpPost("{id:int}/run")]
    public Task<IReadOnlyList<DataSourceRunResult>> Run(int id, CancellationToken ct) => refresh.RunAsync(id, ct);

    [HttpPost("run-all")]
    public Task<IReadOnlyList<DataSourceRunResult>> RunAll(CancellationToken ct) => refresh.RunAllAsync(ct);
}

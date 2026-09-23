using Broli.SOP.Application.Services;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Broli.SOP.API.Controllers;

[ApiController]
[Route("api/mrp")]
[Authorize(Policy = Permissions.SupplyView)]
public sealed class MrpController(MrpService service) : ControllerBase
{
    [HttpGet]
    public Task<MrpDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<PagedResult<MrpRow>> Rows([FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        service.GetRowsAsync(filter, query, ct);
}

/// <summary>Raw materials, films and finished goods: kind = raw-materials | films | finished-goods.</summary>
[ApiController]
[Route("api/materials/{kind}")]
[Authorize(Policy = Permissions.InventoryView)]
public sealed class MaterialsController(MaterialsService service) : ControllerBase
{
    [HttpGet]
    public async Task<ActionResult<MaterialsDashboard>> Get(string kind, [FromQuery] SopFilter filter, CancellationToken ct) =>
        await service.GetDashboardAsync(kind, filter, ct) is { } d ? d : NotFound(new ApiError($"Unknown materials view '{kind}'."));

    [HttpGet("rows")]
    public async Task<ActionResult<PagedResult<MaterialRow>>> Rows(string kind, [FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        await service.GetRowsAsync(kind, filter, query, ct) is { } r ? r : NotFound(new ApiError($"Unknown materials view '{kind}'."));
}

[ApiController]
[Route("api/transit")]
[Authorize(Policy = Permissions.SupplyView)]
public sealed class TransitController(TransitService service) : ControllerBase
{
    [HttpGet]
    public Task<TransitDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<PagedResult<TransitRow>> Rows([FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        service.GetRowsAsync(filter, query, ct);
}

[ApiController]
[Route("api/suppliers")]
[Authorize(Policy = Permissions.SupplyView)]
public sealed class SuppliersController(SupplierService service) : ControllerBase
{
    [HttpGet]
    public Task<SupplierDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<IReadOnlyList<SupplierRow>> Rows([FromQuery] SopFilter filter, CancellationToken ct) => service.GetRowsAsync(filter, ct);
}

using Broli.SOP.Application.Services;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Contracts.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Broli.SOP.API.Controllers;

[ApiController]
[Route("api/executive")]
[Authorize(Policy = Permissions.ExecutiveView)]
public sealed class ExecutiveController(ExecutiveService service) : ControllerBase
{
    [HttpGet]
    public Task<ExecutiveDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetAsync(filter, ct);
}

[ApiController]
[Route("api/demand")]
[Authorize(Policy = Permissions.DemandView)]
public sealed class DemandController(DemandService service) : ControllerBase
{
    [HttpGet]
    public Task<DemandDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<PagedResult<DemandRow>> Rows([FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        service.GetRowsAsync(filter, query, ct);
}

[ApiController]
[Route("api/inventory")]
[Authorize(Policy = Permissions.InventoryView)]
public sealed class InventoryController(InventoryService service) : ControllerBase
{
    [HttpGet]
    public Task<InventoryDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<PagedResult<InventoryRow>> Rows([FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        service.GetRowsAsync(filter, query, ct);
}

[ApiController]
[Route("api/supply")]
[Authorize(Policy = Permissions.SupplyView)]
public sealed class SupplyController(SupplyService service) : ControllerBase
{
    [HttpGet]
    public Task<SupplyDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("rows")]
    public Task<PagedResult<SupplyRow>> Rows([FromQuery] SopFilter filter, [FromQuery] TableQuery query, CancellationToken ct) =>
        service.GetRowsAsync(filter, query, ct);

    [HttpPut("{id:long}")]
    [Authorize(Policy = Permissions.SupplyEdit)]
    public async Task<IActionResult> Update(long id, SupplyUpdateRequest request, CancellationToken ct) =>
        await service.UpdateAsync(id, request, ct) ? NoContent() : NotFound();
}

[ApiController]
[Route("api/risks")]
[Authorize(Policy = Permissions.RisksView)]
public sealed class RisksController(RiskService service) : ControllerBase
{
    [HttpGet]
    public Task<RiskDashboard> Get([FromQuery] SopFilter filter, CancellationToken ct) => service.GetDashboardAsync(filter, ct);

    [HttpGet("register")]
    public Task<PagedResult<RiskItemDto>> Register([FromQuery] TableQuery query, CancellationToken ct) => service.GetRegisterAsync(query, ct);

    [HttpPost("register")]
    [Authorize(Policy = Permissions.RisksEdit)]
    public Task<RiskItemDto> Create(RiskItemUpsert request, CancellationToken ct) => service.CreateAsync(request, ct);

    [HttpPut("register/{id:int}")]
    [Authorize(Policy = Permissions.RisksEdit)]
    public async Task<ActionResult<RiskItemDto>> Update(int id, RiskItemUpsert request, CancellationToken ct) =>
        await service.UpdateAsync(id, request, ct) is { } dto ? dto : NotFound();
}

[ApiController]
[Route("api/products")]
[Authorize(Policy = Permissions.InventoryView)]
public sealed class ProductsController(ProductService service) : ControllerBase
{
    [HttpGet("{cartSap}")]
    public async Task<ActionResult<ProductDetail>> Get(string cartSap, [FromQuery] SopFilter filter, CancellationToken ct) =>
        await service.GetAsync(cartSap, filter, ct) is { } detail ? detail : NotFound(new ApiError($"Product '{cartSap}' not found."));
}

[ApiController]
[Route("api")]
public sealed class ReferenceController(ReferenceService service) : ControllerBase
{
    [HttpGet("filters/options")]
    public Task<FilterOptions> Options(CancellationToken ct) => service.GetFilterOptionsAsync(ct);

    [HttpGet("search")]
    public Task<IReadOnlyList<SearchResult>> Search([FromQuery] string? q, CancellationToken ct) => service.SearchAsync(q, ct);

    [HttpGet("data/status")]
    public Task<DataStatus> Status(CancellationToken ct) => service.GetDataStatusAsync(ct);
}

[ApiController]
[Route("api/export")]
[Authorize(Policy = Permissions.DataExport)]
public sealed class ExportController(ExportService service) : ControllerBase
{
    /// <summary>Exports the filtered rows of a table (all pages). format = xlsx | csv.</summary>
    [HttpGet("{dataset}")]
    public async Task<IActionResult> Export(string dataset, [FromQuery] SopFilter filter, [FromQuery] TableQuery query,
        [FromQuery] string format = "xlsx", CancellationToken ct = default)
    {
        var required = dataset switch
        {
            "risk-register" or "risks" => Permissions.RisksView,
            "supply" or "mrp" or "transit" or "suppliers" => Permissions.SupplyView,
            "demand" => Permissions.DemandView,
            "actions" => Permissions.ActionsView,
            _ => Permissions.InventoryView,
        };
        if (!User.HasClaim(Broli.SOP.Infrastructure.JwtTokenService.PermissionClaim, required)) return Forbid();
        var file = await service.ExportAsync(dataset, format, filter, query, ct);
        return file is { } f ? File(f.Content, f.ContentType, f.FileName) : NotFound(new ApiError($"Unknown dataset '{dataset}'."));
    }
}

using Broli.SOP.Contracts;
using Broli.SOP.Web.Services;
using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.JSInterop;

namespace Broli.SOP.Web.Components.Shared;

/// <summary>
/// Base for analytical pages: reloads when the global filter changes, cancels stale requests,
/// exposes loading/error state, and applies drill-down parameters (?brand=, ?category=, ?supplier=) to the filter bar.
/// </summary>
public abstract class SopPage : ComponentBase, IDisposable
{
    [Inject] protected ApiClient Api { get; set; } = default!;
    [Inject] protected FilterState Filters { get; set; } = default!;
    [Inject] protected AuthSession Session { get; set; } = default!;
    [Inject] protected NavigationManager Nav { get; set; } = default!;
    [Inject] protected IJSRuntime JS { get; set; } = default!;
    [Inject] protected UiState Ui { get; set; } = default!;

    protected bool Loading { get; private set; } = true;
    protected string? Error { get; private set; }
    private CancellationTokenSource? _cts;

    protected SopFilter Filter => Filters.Filter;

    protected override async Task OnInitializedAsync()
    {
        await ApplyDrillDownAsync();
        Filters.Changed += OnFilterChanged;
    }

    protected override Task OnParametersSetAsync() => ReloadAsync();

    private async Task OnFilterChanged() => await InvokeAsync(ReloadAsync);

    protected async Task ReloadAsync()
    {
        _cts?.Cancel();
        var cts = _cts = new CancellationTokenSource();
        Loading = true;
        Error = null;
        StateHasChanged();
        using var busy = Ui.BeginBusy();
        try
        {
            await LoadAsync(cts.Token);
        }
        catch (OperationCanceledException) when (cts.IsCancellationRequested)
        {
            return;
        }
        catch (ApiException ex)
        {
            Error = ex.Full;
        }
        catch (Exception ex)
        {
            Error = "Une erreur est survenue lors du chargement de cette page.";
            Console.Error.WriteLine(ex);
        }
        if (cts.IsCancellationRequested) return;
        Loading = false;
        StateHasChanged();
    }

    protected abstract Task LoadAsync(CancellationToken ct);

    private async Task ApplyDrillDownAsync()
    {
        var query = QueryHelpers.ParseQuery(new Uri(Nav.Uri).Query);
        string? Q(string k) => query.TryGetValue(k, out var v) && !string.IsNullOrWhiteSpace(v) ? v.ToString() : null;
        var brand = Q("brand");
        var category = Q("category");
        var supplier = Q("supplier");
        var product = Q("product");
        if (brand is null && category is null && supplier is null && product is null) return;
        await Filters.UpdateAsync(f =>
        {
            if (brand is not null) f.Brands = [brand];
            if (category is not null) f.Categories = [category];
            if (supplier is not null) f.Suppliers = [supplier];
            if (product is not null) f.Products = [product];
        });
    }

    protected Task DownloadAsync(string dataset, string format, TableQuery query) => ExportHelper.ExportAsync(Api, JS, dataset, format, Filter, query);

    protected void Go(string url) => Nav.NavigateTo(url);

    public virtual void Dispose()
    {
        Filters.Changed -= OnFilterChanged;
        _cts?.Cancel();
        GC.SuppressFinalize(this);
    }
}

public static class ExportHelper
{
    public static async Task ExportAsync(ApiClient api, IJSRuntime js, string dataset, string format, SopFilter? filter, TableQuery query)
    {
        var all = new TableQuery { Search = query.Search, View = query.View, Sort = query.Sort, Desc = query.Desc, PageSize = TableQuery.MaxPageSize };
        var (content, name) = await api.DownloadAsync($"api/export/{dataset}", filter, all, $"format={format}");
        using var stream = new MemoryStream(content);
        using var streamRef = new DotNetStreamReference(stream);
        var type = format == "csv" ? "text/csv" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
        await js.InvokeVoidAsync("sop.download", name, type, streamRef);
    }
}

using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Microsoft.AspNetCore.Components.Server.ProtectedBrowserStorage;

namespace Broli.SOP.Web.Services;

/// <summary>
/// The persistent global filter bar. Pages subscribe to <see cref="Changed"/> and reload;
/// the selection survives navigation and page refreshes (stored per browser).
/// </summary>
public sealed class FilterState(ProtectedLocalStorage storage, ILogger<FilterState> logger)
{
    private const string Key = "sop.filter";

    public SopFilter Filter { get; private set; } = new();
    private FilterOptions? _options;

    /// <summary>Options for the filter controls. Setting them notifies <see cref="OptionsChanged"/>.</summary>
    public FilterOptions? Options
    {
        get => _options;
        set { _options = value; OptionsChanged?.Invoke(); }
    }

    public event Action? OptionsChanged;
    public bool Restored { get; private set; }

    public event Func<Task>? Changed;

    public async Task RestoreAsync()
    {
        if (Restored) return;
        try
        {
            var r = await storage.GetAsync<SopFilter>(Key);
            if (r is { Success: true, Value: { } f }) Filter = f;
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "Could not restore filters");
        }
        Restored = true;
    }

    public async Task UpdateAsync(Action<SopFilter> mutate)
    {
        var copy = Filter.Clone();
        mutate(copy);
        Filter = copy;
        await PersistAsync();
        await NotifyAsync();
    }

    public Task ResetAsync() => UpdateAsync(f =>
    {
        f.Year = null; f.Months.Clear(); f.Agencies.Clear(); f.Categories.Clear(); f.Products.Clear(); f.Brands.Clear();
        f.Suppliers.Clear(); f.Countries.Clear(); f.MaterialTypes.Clear(); f.Statuses.Clear();
    });

    private async Task PersistAsync()
    {
        try { await storage.SetAsync(Key, Filter); }
        catch (Exception ex) { logger.LogDebug(ex, "Could not persist filters"); }
    }

    private async Task NotifyAsync()
    {
        if (Changed is null) return;
        foreach (var handler in Changed.GetInvocationList().Cast<Func<Task>>())
        {
            try { await handler(); }
            catch (Exception ex) { logger.LogWarning(ex, "Filter change handler failed"); }
        }
    }

    /// <summary>Label for a filter value, from the loaded options.</summary>
    public string LabelOf(string dimension, string value)
    {
        IEnumerable<Option>? list = dimension switch
        {
            "Agency" => Options?.Agencies,
            "Family" => Options?.Categories,
            "Brand" => Options?.Brands,
            "Supplier" => Options?.Suppliers,
            "Country" => Options?.Countries,
            "Material" => Options?.MaterialTypes,
            "Status" => Options?.Statuses,
            _ => null,
        };
        return list?.FirstOrDefault(o => o.Value == value)?.Label ?? value;
    }
}

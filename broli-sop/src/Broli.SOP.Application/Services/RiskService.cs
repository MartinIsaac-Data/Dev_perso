namespace Broli.SOP.Application.Services;

public sealed class RiskService(
    IAnalyticsEngine engine,
    IRiskRepository repository,
    IAuditLogger audit,
    ICurrentUser user,
    IClock clock)
{
    public async Task<RiskDashboard> GetDashboardAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        var detected = RiskDetector.Detect(s, s.FilterLines(filter));
        var register = await VisibleAsync(ct);
        var today = clock.Today;

        return new RiskDashboard(
            s.Period.Info,
            detected.Count,
            detected.Count(d => d.Severity == "Critical"),
            register.Count(r => r.Status != RiskStatus.Closed),
            register.Count(r => r.Status != RiskStatus.Closed && r.DueDate is { } d && d < today),
            detected.GroupBy(d => d.Category).OrderByDescending(g => g.Count())
                .Select(g => new ChartPoint(g.Key, g.Count(), g.Key)).ToList(),
            Enum.GetValues<RiskStatus>().Select(st => new ChartPoint(Labels.Of(st), register.Count(r => r.Status == st), st.ToString())).ToList(),
            detected.Take(500).ToList());
    }

    public async Task<IReadOnlyList<DetectedRisk>> GetDetectedAsync(SopFilter filter, CancellationToken ct)
    {
        var s = await engine.GetSnapshotAsync(filter, ct);
        return RiskDetector.Detect(s, s.FilterLines(filter));
    }

    public async Task<PagedResult<RiskItemDto>> GetRegisterAsync(TableQuery q, CancellationToken ct)
    {
        var rows = await RegisterRowsAsync(q, ct);
        return TableHelper.Page(rows, q, SortKeys, Search, "Score", true);
    }

    public async Task<IReadOnlyList<RiskItemDto>> GetAllRegisterAsync(TableQuery q, CancellationToken ct)
    {
        var rows = await RegisterRowsAsync(q, ct);
        return TableHelper.Sort(TableHelper.Filter(rows, q, Search), q, SortKeys, "Score", true).ToList();
    }

    private async Task<IEnumerable<RiskItemDto>> RegisterRowsAsync(TableQuery q, CancellationToken ct)
    {
        var today = clock.Today;
        var rows = (await VisibleAsync(ct)).Select(r => r.ToDto(today));
        return q.View?.ToLowerInvariant() switch
        {
            "open" => rows.Where(r => r.Status != "Closed"),
            "overdue" => rows.Where(r => r.IsOverdue),
            "closed" => rows.Where(r => r.Status == "Closed"),
            "opportunities" => rows.Where(r => r.IsOpportunity),
            _ => rows,
        };
    }

    /// <summary>Register items about products outside the user's data scope are hidden.</summary>
    private async Task<IEnumerable<RiskItem>> VisibleAsync(CancellationToken ct) =>
        (await repository.ListAsync(ct)).Where(r => r.Product is null || DataScope.AllowsCategory(user, r.Product.Category?.Code)).ToList();

    private static string Search(RiskItemDto r) => $"{r.Code} {r.Category} {r.Description} {r.CArtSap} {r.Product} {r.Owner} {r.Action}";

    private static readonly Dictionary<string, Func<RiskItemDto, object?>> SortKeys = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Code"] = r => r.Code,
        ["Category"] = r => r.Category,
        ["Description"] = r => r.Description,
        ["Product"] = r => r.CArtSap,
        ["Impact"] = r => r.Impact,
        ["Probability"] = r => r.Probability,
        ["Score"] = r => r.Score,
        ["Owner"] = r => r.Owner,
        ["DueDate"] = r => r.DueDate,
        ["Status"] = r => r.Status,
    };

    public async Task<RiskItemDto> CreateAsync(RiskItemUpsert request, CancellationToken ct)
    {
        var item = new RiskItem { Code = await repository.NextCodeAsync(ct), CreatedAtUtc = clock.UtcNow, CreatedBy = user.Username };
        await ApplyAsync(item, request, ct);
        repository.Add(item);
        await repository.SaveChangesAsync(ct);
        await audit.LogAsync("Created risk", "Risks", item.Code, null, Describe(item), ct);
        var saved = await repository.FindAsync(item.Id, ct);
        return (saved ?? item).ToDto(clock.Today);
    }

    public async Task<RiskItemDto?> UpdateAsync(int id, RiskItemUpsert request, CancellationToken ct)
    {
        var item = await repository.FindAsync(id, ct);
        if (item is null) return null;
        var before = Describe(item);
        await ApplyAsync(item, request, ct);
        item.UpdatedAtUtc = clock.UtcNow;
        await repository.SaveChangesAsync(ct);
        var after = Describe(item);
        if (before != after) await audit.LogAsync("Updated risk", "Risks", item.Code, before, after, ct);
        var saved = await repository.FindAsync(id, ct);
        return saved?.ToDto(clock.Today);
    }

    private async Task ApplyAsync(RiskItem item, RiskItemUpsert r, CancellationToken ct)
    {
        var errors = new List<string>();
        if (!Labels.TryParse<RiskCategory>(r.Category, out var category)) errors.Add($"Unknown category '{r.Category}'.");
        if (!Labels.TryParse<ImpactLevel>(r.Impact, out var impact)) errors.Add($"Unknown impact '{r.Impact}'.");
        if (!Labels.TryParse<RiskStatus>(r.Status, out var status)) errors.Add($"Unknown status '{r.Status}'.");
        if (string.IsNullOrWhiteSpace(r.Description)) errors.Add("Description is required.");
        if (string.IsNullOrWhiteSpace(r.Owner)) errors.Add("Owner is required.");
        if (r.Probability is < 0 or > 100) errors.Add("Probability must be between 0 and 100.");

        int? productId = null, supplierId = null;
        if (!string.IsNullOrWhiteSpace(r.CArtSap))
        {
            productId = await repository.ProductIdAsync(r.CArtSap.Trim(), ct);
            if (productId is null) errors.Add($"Unknown CArtSAP '{r.CArtSap}'.");
        }
        if (!string.IsNullOrWhiteSpace(r.SupplierCode))
        {
            supplierId = await repository.SupplierIdAsync(r.SupplierCode.Trim(), ct);
            if (supplierId is null) errors.Add($"Unknown supplier '{r.SupplierCode}'.");
        }
        if (errors.Count > 0) throw new ValidationException(errors);

        item.Category = category;
        item.IsOpportunity = r.IsOpportunity;
        item.Description = r.Description.Trim();
        item.ProductId = productId;
        item.SupplierId = supplierId;
        item.Impact = impact;
        item.Probability = r.Probability;
        item.Owner = r.Owner.Trim();
        item.Action = r.Action?.Trim();
        item.DueDate = r.DueDate;
        item.Status = status;
    }

    private static string Describe(RiskItem r) =>
        $"{Labels.Of(r.Category)} | {r.Description} | impact {Labels.Of(r.Impact)} | p {r.Probability}% | {r.Owner} | due {r.DueDate:dd/MM/yyyy} | {Labels.Of(r.Status)}";
}

/// <summary>Input rejected by business validation. The API maps it to HTTP 400 with the messages.</summary>
public sealed class ValidationException(IReadOnlyList<string> errors) : Exception(string.Join(" ", errors))
{
    public IReadOnlyList<string> Errors { get; } = errors;
}

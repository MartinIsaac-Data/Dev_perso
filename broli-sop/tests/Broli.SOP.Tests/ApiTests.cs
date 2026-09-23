using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using ClosedXML.Excel;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Broli.SOP.Tests;

/// <summary>Runs the real API on a throw-away SQLite file with generated DEMO data.</summary>
public class ApiFactory : WebApplicationFactory<Program>
{
    public const string AdminPassword = "Admin#Test2026";
    public const string DemoPassword = "Demo#Test2026";
    private readonly string _db = Path.Combine(Path.GetTempPath(), $"broli-sop-test-{Guid.NewGuid():N}.db");

    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { Converters = { new JsonStringEnumConverter() } };

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.UseSetting("ConnectionStrings:Sop", $"Data Source={_db}");
        builder.UseSetting("Database:Provider", "Sqlite");
        builder.UseSetting("Demo:Enabled", "true");
        builder.UseSetting("Bootstrap:AdminUsername", "admin");
        builder.UseSetting("Bootstrap:AdminPassword", AdminPassword);
        builder.UseSetting("Demo:UserPassword", DemoPassword);
        builder.UseSetting("Refresh:Enabled", "false"); // tests trigger refreshes and alerts explicitly
        Configure(builder);
    }

    protected virtual void Configure(IWebHostBuilder builder) { }

    public async Task<HttpClient> ClientAsync(string user = "admin", string? password = null)
    {
        var client = CreateClient();
        var response = await client.PostAsJsonAsync("api/auth/login", new LoginRequest(user, password ?? (user == "admin" ? AdminPassword : DemoPassword)));
        response.EnsureSuccessStatusCode();
        var login = await response.Content.ReadFromJsonAsync<LoginResponse>(Json);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login!.Token);
        return client;
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
        foreach (var f in new[] { _db, _db + "-wal", _db + "-shm" }) try { File.Delete(f); } catch (IOException) { }
    }
}

public static class HttpJson
{
    public static async Task<T> Get<T>(this HttpClient c, string url)
    {
        var r = await c.GetAsync(url);
        Assert.True(r.IsSuccessStatusCode, $"{url} → {(int)r.StatusCode} {await r.Content.ReadAsStringAsync()}");
        return (await r.Content.ReadFromJsonAsync<T>(ApiFactory.Json))!;
    }
}

public class ApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private const string Scenario = "year={0}&months={1}&categories=FILMS&brands=Rahma";

    [Fact]
    public async Task Anonymous_calls_are_rejected_but_health_is_public()
    {
        var c = factory.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.GetAsync("api/executive")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("health")).StatusCode);
    }

    [Fact]
    public async Task Wrong_password_is_rejected_and_repeated_failures_lock_the_account()
    {
        var c = factory.CreateClient();
        for (var i = 0; i < 5; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await c.PostAsJsonAsync("api/auth/login", new LoginRequest("production", "wrong-password1"))).StatusCode);
        // Correct password is now refused too: the account is locked.
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.PostAsJsonAsync("api/auth/login", new LoginRequest("production", ApiFactory.DemoPassword))).StatusCode);
    }

    [Fact]
    public async Task Executive_dashboard_returns_ten_finite_kpis()
    {
        var c = await factory.ClientAsync("dg");
        var d = await c.Get<ExecutiveDashboard>("api/executive");
        Assert.Equal(10, d.Kpis.Count);
        Assert.All(d.Kpis, k => Assert.True(k.Value is null || double.IsFinite(k.Value.Value), k.Code));
        Assert.All(d.Kpis, k => Assert.True(k.ChangePct is null || double.IsFinite(k.ChangePct.Value), k.Code));
        Assert.True(d.IsDemoData);
        Assert.Contains(d.Kpis, k => k.Code == "STOCK_AT_RISK" && k.DrillUrl.Contains("at-risk"));
    }

    [Fact]
    public async Task Priority_scenario_films_rahma_leads_to_an_expedite_action()
    {
        var c = await factory.ClientAsync("dg");
        var today = DateTime.Today;
        var q = string.Format(Scenario, today.Year, today.Month);

        var all = await c.Get<ExecutiveDashboard>("api/executive");
        var scoped = await c.Get<ExecutiveDashboard>($"api/executive?{q}");
        double Kpi(ExecutiveDashboard d, string code) => d.Kpis.First(k => k.Code == code).Value ?? 0;
        Assert.True(Kpi(scoped, "TOTAL_STOCK") < Kpi(all, "TOTAL_STOCK"), "filters must change the KPIs");
        Assert.True(Kpi(scoped, "STOCK_AT_RISK") >= 1);

        var atRisk = await c.Get<PagedResult<InventoryRow>>($"api/inventory/rows?{q}&view=at-risk");
        Assert.NotEmpty(atRisk.Items);
        Assert.All(atRisk.Items, r => { Assert.Equal("Films", r.Category); Assert.Equal("Rahma", r.Brand); Assert.True(r.AtRisk); });

        var critical = atRisk.Items.First(r => r.CoverageStatus == "Critical");
        var detail = await c.Get<ProductDetail>($"api/products/{critical.CArtSap}?{q}");
        Assert.NotEmpty(detail.OpenOrders);
        Assert.Contains(detail.OpenOrders, o => o.Eta.HasValue && o.RiskLevel == "Critical");
        Assert.StartsWith("Expedite PO", detail.Actions[0].Title);
    }

    [Fact]
    public async Task Roles_restrict_views_and_financial_values()
    {
        var sales = await factory.ClientAsync("sales");
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/supply")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/admin/users")).StatusCode);
        var salesRows = await sales.Get<PagedResult<InventoryRow>>("api/inventory/rows?pageSize=50");
        Assert.All(salesRows.Items, r => Assert.Null(r.StockValue));

        var finance = await factory.ClientAsync("finance");
        var financeRows = await finance.Get<PagedResult<InventoryRow>>("api/inventory/rows?pageSize=50");
        Assert.Contains(financeRows.Items, r => r.StockValue > 0);

        var warehouse = await factory.ClientAsync("warehouse");
        Assert.Equal(HttpStatusCode.Forbidden, (await warehouse.PutAsJsonAsync("api/settings", new { })).StatusCode);
    }

    [Fact]
    public async Task Tables_are_paged_and_sorted_server_side()
    {
        var c = await factory.ClientAsync();
        var page = await c.Get<PagedResult<InventoryRow>>("api/inventory/rows?page=2&pageSize=10&sort=CoverageMonths&desc=false");
        Assert.Equal(10, page.Items.Count);
        Assert.True(page.Total > 100);
        var covered = page.Items.Where(r => r.CoverageMonths.HasValue).Select(r => r.CoverageMonths!.Value).ToList();
        Assert.Equal(covered.Order(), covered);
    }

    [Fact]
    public async Task Search_finds_products_suppliers_and_brands()
    {
        var c = await factory.ClientAsync("dg");
        var r = await c.Get<List<SearchResult>>("api/search?q=rahma");
        Assert.Contains(r, x => x.Type == "Product");
        Assert.Contains(r, x => x.Type == "Brand" && x.Key == "Rahma");
        Assert.Empty(await c.Get<List<SearchResult>>("api/search?q=r"));
    }

    [Fact]
    public async Task Export_returns_only_the_filtered_rows_as_xlsx()
    {
        var c = await factory.ClientAsync("dg");
        var today = DateTime.Today;
        var response = await c.GetAsync($"api/export/inventory?{string.Format(Scenario, today.Year, today.Month)}&view=at-risk&format=xlsx");
        response.EnsureSuccessStatusCode();
        Assert.Equal("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response.Content.Headers.ContentType?.MediaType);
        using var wb = new XLWorkbook(await response.Content.ReadAsStreamAsync());
        var rows = wb.Worksheet(1).RowsUsed().Skip(3).ToList(); // title, subtitle, date, header
        Assert.All(rows.Skip(1), r => Assert.Equal("Films", r.Cell(3).GetString()));

        var csv = await c.GetAsync("api/export/demand?format=csv");
        Assert.Equal("text/csv", csv.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task Updating_an_eta_is_audited_and_invalid_dates_are_refused()
    {
        var c = await factory.ClientAsync();
        var line = (await c.Get<PagedResult<SupplyRow>>("api/supply/rows?view=open&pageSize=1")).Items[0];
        var newEta = (line.Eta ?? DateOnly.FromDateTime(DateTime.Today)).AddDays(7);

        var ok = await c.PutAsJsonAsync($"api/supply/{line.Id}", new SupplyUpdateRequest(null, newEta, null, null, null), ApiFactory.Json);
        Assert.Equal(HttpStatusCode.NoContent, ok.StatusCode);
        var audit = await c.Get<PagedResult<AuditEntryDto>>($"api/admin/audit?search={line.PoNumber}");
        Assert.Contains(audit.Items, a => a.Action == "Updated ETA" && a.NewValue == newEta.ToString("dd/MM/yyyy"));

        var bad = await c.PutAsJsonAsync($"api/supply/{line.Id}", new SupplyUpdateRequest(newEta.AddDays(30), null, null, null, null), ApiFactory.Json);
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
    }

    [Fact]
    public async Task Configuration_is_validated()
    {
        var c = await factory.ClientAsync();
        var s = await c.Get<SettingsDto>("api/settings");
        s.Coverage.RiskBelowMonths = 0.2; // below Critical: thresholds no longer increase
        var r = await c.PutAsJsonAsync("api/settings", s, ApiFactory.Json);
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Contains("must increase", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Risk_register_can_be_created_and_rejects_unknown_products()
    {
        var c = await factory.ClientAsync("supply");
        var ok = await c.PostAsJsonAsync("api/risks/register",
            new RiskItemUpsert("Supply Delay", false, "Test risk", null, null, "High", 60, "Supply", "Follow up", DateOnly.FromDateTime(DateTime.Today), "Open"));
        Assert.True(ok.IsSuccessStatusCode, await ok.Content.ReadAsStringAsync());
        var bad = await c.PostAsJsonAsync("api/risks/register",
            new RiskItemUpsert("Stockout", false, "Bad", "NOPE-1", null, "High", 60, "Supply", null, null, "Open"));
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
    }
}

/// <summary>Import is destructive (purges DEMO data), so it gets its own database.</summary>
public class ImportApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private static MultipartFormDataContent Xlsx(string sheet, string[] headers, params object?[][] rows)
    {
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add(sheet);
        for (var c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
        for (var r = 0; r < rows.Length; r++)
            for (var c = 0; c < rows[r].Length; c++)
                ws.Cell(r + 2, c + 1).Value = rows[r][c] switch { null => Blank.Value, DateTime d => d, double d => d, var o => o.ToString() };
        var ms = new MemoryStream();
        wb.SaveAs(ms);
        var form = new MultipartFormDataContent();
        form.Add(new ByteArrayContent(ms.ToArray()), "file", $"{sheet}.xlsx");
        return form;
    }

    private static async Task<ImportPreview> Preview(HttpClient c, string type, MultipartFormDataContent form)
    {
        var r = await c.PostAsync($"api/imports/preview/{type}", form);
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        return (await r.Content.ReadFromJsonAsync<ImportPreview>(ApiFactory.Json))!;
    }

    [Fact]
    public async Task Excel_import_flow_blocks_errors_then_replaces_demo_with_real_data()
    {
        var c = await factory.ClientAsync();
        var sales = await factory.ClientAsync("sales");
        Assert.Equal(HttpStatusCode.Forbidden, (await sales.GetAsync("api/imports/templates")).StatusCode);

        // Templates download as real workbooks.
        var template = await c.GetAsync("api/imports/templates/supply");
        using (var wb = new XLWorkbook(await template.Content.ReadAsStreamAsync()))
            Assert.Equal("PO", wb.Worksheet(1).Cell(1, 1).GetString());

        // Facts cannot be imported while only DEMO products exist.
        var early = await Preview(c, "inventory", Xlsx("INVENTORY", ["Date", "CArtSAP", "Stock", "Warehouse"], [new DateTime(2026, 9, 30), "100245", 10.0, "Douala"]));
        Assert.False(early.CanCommit);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsync($"api/imports/{early.Id}/commit", null)).StatusCode);

        // Supplier master → purges DEMO data.
        var suppliers = await Preview(c, "supplier-master", Xlsx("SUPPLIER MASTER", ["Supplier Code", "Supplier Name", "Country"], ["SUP-1", "Anatolia Films", "Turkey"]));
        Assert.True(suppliers.CanCommit);
        Assert.True(suppliers.WillPurgeDemoData);
        var committed = await (await c.PostAsync($"api/imports/{suppliers.Id}/commit", null)).Content.ReadFromJsonAsync<ImportResult>(ApiFactory.Json);
        Assert.True(committed!.PurgedDemoData);
        var status = await c.Get<DataStatus>("api/data/status");
        Assert.False(status.HasDemoData);
        Assert.Equal(1, status.RowCounts["Suppliers"]);

        // Product master, then a stock file with one invalid row: nothing is imported until it is fixed.
        var products = await Preview(c, "product-master", Xlsx("PRODUCT MASTER", ["CArtSAP", "Description", "Category", "Material Type", "Brand", "TC Conversion", "Main Supplier"],
            ["300101", "FILM RAHMA SPAGHETTI 500G", "FILMS", "Packaging", "Rahma", 18000.0, "SUP-1"]));
        Assert.True(products.CanCommit, string.Join("; ", products.Issues.Select(i => i.Message)));
        await c.PostAsync($"api/imports/{products.Id}/commit", null);

        var badStock = await Preview(c, "inventory", Xlsx("INVENTORY", ["Date", "CArtSAP", "Stock", "Warehouse"],
            [new DateTime(2026, 8, 31), "300101", 9000.0, "Plant"], [new DateTime(2026, 9, 30), "300101", -1.0, "Plant"]));
        Assert.False(badStock.CanCommit);
        Assert.Equal(1, badStock.ErrorCount);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsync($"api/imports/{badStock.Id}/commit", null)).StatusCode);
        Assert.Equal(0, (await c.Get<DataStatus>("api/data/status")).RowCounts["FACT_INVENTORY"]);

        var goodStock = await Preview(c, "inventory", Xlsx("INVENTORY", ["Date", "CArtSAP", "Stock", "Warehouse"],
            [new DateTime(2026, 8, 31), "300101", 9000.0, "Plant"], [new DateTime(2026, 9, 30), "300101", 7000.0, "Plant"]));
        Assert.True(goodStock.CanCommit);
        await c.PostAsync($"api/imports/{goodStock.Id}/commit", null);

        var inv = await c.Get<PagedResult<InventoryRow>>("api/inventory/rows?year=2026&months=9");
        var row = Assert.Single(inv.Items);
        Assert.Equal(7000, row.ClosingStock);
        Assert.Equal(9000, row.OpeningStock);
        Assert.Equal("No Demand", row.CoverageStatus); // no sales / forecast imported yet: never NaN or Infinity

        var history = await c.Get<List<ImportBatchDto>>("api/imports/history");
        Assert.Equal(3, history.Count);
    }
}

using System.Net;
using System.Net.Http.Json;
using Broli.SOP.Application.Analytics;
using Broli.SOP.Application.Import;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Broli.SOP.Data;
using Broli.SOP.Domain.Entities;
using Broli.SOP.Domain.Enums;
using ClosedXML.Excel;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Broli.SOP.Tests;

public class DataScopeTests
{
    private sealed class User(string[] agencies, string[] categories) : Application.Abstractions.ICurrentUser
    {
        public string Username => "u";
        public bool IsAuthenticated => true;
        public bool Has(string permission) => true;
        public IReadOnlyList<string> ScopeAgencies => agencies;
        public IReadOnlyList<string> ScopeCategories => categories;
    }

    [Fact]
    public void Unrestricted_users_keep_their_filter()
    {
        var f = new SopFilter { Categories = ["SPAGHETTI"] };
        Assert.Same(f, DataScope.Apply(f, new User([], [])));
    }

    [Fact]
    public void Scope_fills_an_empty_selection_and_intersects_an_explicit_one()
    {
        var u = new User(["DLA"], ["FILMS", "OILS"]);
        var all = DataScope.Apply(new SopFilter(), u);
        Assert.Equal(["DLA"], all.Agencies);
        Assert.Equal(["FILMS", "OILS"], all.Categories);

        Assert.Equal(["FILMS"], DataScope.Apply(new SopFilter { Categories = ["FILMS", "SPAGHETTI"] }, u).Categories);
        Assert.Equal([DataScope.NoAccess], DataScope.Apply(new SopFilter { Categories = ["SPAGHETTI"] }, u).Categories);
    }

    [Theory]
    [InlineData("06:00", "2026-09-23 05:59", null, false)]
    [InlineData("06:00", "2026-09-23 06:00", null, true)]
    [InlineData("06:00", "2026-09-23 09:00", "2026-09-23 06:01", false)]
    [InlineData("06:00", "2026-09-24 06:30", "2026-09-23 06:01", true)]
    [InlineData(null, "2026-09-23 09:00", null, false)]
    public void Sources_run_once_a_day_after_their_time(string? at, string now, string? lastLocal, bool due)
    {
        var s = new DataSource { DailyAt = at, LastRunUtc = lastLocal is null ? null : DateTime.Parse(lastLocal).ToUniversalTime() };
        Assert.Equal(due, DataRefreshService.IsDue(s, DateTime.Parse(now)));
    }
}

public class SqlServerMigrationTests
{
    private static SopDbContext SqlServerContext() =>
        new(new DbContextOptionsBuilder<SopDbContext>().UseSqlServer("Server=(none);Database=BroliSOP;Trusted_Connection=True").Options);

    [Fact]
    public void Migrations_are_in_sync_with_the_model()
    {
        using var db = SqlServerContext();
        Assert.False(db.Database.HasPendingModelChanges(), "Run: dotnet ef migrations add <Name> --project src/Broli.SOP.Data --output-dir Migrations/SqlServer");
        Assert.NotEmpty(db.Database.GetMigrations());
    }

    [Fact]
    public void Sql_server_schema_contains_every_table()
    {
        using var db = SqlServerContext();
        var script = db.Database.GenerateCreateScript();
        foreach (var t in new[] { "DIM_PRODUCT", "FACT_SALES", "FACT_SUPPLY", "SOP_ACTION", "SYS_NOTIFICATION", "SYS_DATA_SOURCE", "SEC_USER" })
            Assert.Contains($"[{t}]", script);
    }
}

public class Phase3ApiTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private static ActionUpsert NewAction(string owner, bool decision = false, string? risk = null, int dueInDays = 5) =>
        new(null, "Test topic", "Do something", owner, "Supply Chain", DateOnly.FromDateTime(DateTime.Today.AddDays(dueInDays)), "High", "Open", null, decision, risk, null);

    [Fact]
    public async Task Actions_can_be_tracked_filtered_and_are_permissioned()
    {
        var supply = await factory.ClientAsync("supply");
        var created = await (await supply.PostAsJsonAsync("api/actions", NewAction("Responsable commercial (DÉMO)", decision: true, risk: "R-0001"), ApiFactory.Json))
            .Content.ReadFromJsonAsync<ActionDto>(ApiFactory.Json);
        Assert.StartsWith("A-", created!.Code);
        Assert.Equal("R-0001", created.RiskCode);

        // The owner is notified in the application.
        var sales = await factory.ClientAsync("sales");
        var feed = await sales.Get<NotificationFeed>("api/notifications");
        Assert.Contains(feed.Items, n => n.Title.Contains(created.Code));

        var update = await supply.PutAsJsonAsync($"api/actions/{created.Id}",
            NewAction("Responsable commercial (DÉMO)", decision: true) with { Status = "Done", Comment = "Handled" }, ApiFactory.Json);
        Assert.True(update.IsSuccessStatusCode);
        var done = await supply.Get<PagedResult<ActionDto>>("api/actions?view=done&pageSize=100");
        Assert.Contains(done.Items, a => a.Code == created.Code && a.Comment == "Handled");

        var overdue = await supply.Get<PagedResult<ActionDto>>("api/actions?view=overdue&pageSize=100");
        Assert.All(overdue.Items, a => Assert.True(a.IsOverdue));
        var byDept = await supply.Get<PagedResult<ActionDto>>("api/actions?view=all&department=Direction&pageSize=100");
        Assert.All(byDept.Items, a => Assert.Equal("Direction", a.Department));

        var bad = await supply.PostAsJsonAsync("api/actions", NewAction("", risk: "R-9999"), ApiFactory.Json);
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        var body = await bad.Content.ReadAsStringAsync();
        Assert.Contains("Le responsable est obligatoire", body);
        Assert.Contains("Risque inconnu", body);

        var finance = await factory.ClientAsync("finance");
        Assert.Equal(HttpStatusCode.OK, (await finance.GetAsync("api/actions")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await finance.PostAsJsonAsync("api/actions", NewAction("x"), ApiFactory.Json)).StatusCode);
    }

    [Fact]
    public async Task Meeting_view_has_every_section_and_open_decisions()
    {
        var dg = await factory.ClientAsync("dg");
        var m = await dg.Get<MeetingView>("api/meeting");
        foreach (var s in new[] { m.Demand, m.Supply, m.Inventory, m.Logistics, m.Risks, m.Opportunities })
        {
            Assert.NotEmpty(s.Kpis);
            Assert.All(s.Kpis, k => Assert.DoesNotContain("NaN", k.Value));
        }
        Assert.NotEmpty(m.Decisions);
        Assert.All(m.Decisions, d => Assert.True(d.IsDecision && d.Status is "Ouverte" or "En cours"));
    }

    [Fact]
    public async Task Alerts_notify_the_right_people_once()
    {
        var admin = await factory.ClientAsync();
        var first = await (await admin.PostAsync("api/alerts/run", null)).Content.ReadFromJsonAsync<AlertRunResult>(ApiFactory.Json);
        Assert.True(first!.Alerts > 0);
        var second = await (await admin.PostAsync("api/alerts/run", null)).Content.ReadFromJsonAsync<AlertRunResult>(ApiFactory.Json);
        Assert.Equal(0, second!.Alerts);

        var logistics = await factory.ClientAsync("logistics");
        var feed = await logistics.Get<NotificationFeed>("api/notifications");
        Assert.Contains(feed.Items, n => n.Kind == "eta");
        Assert.True(feed.Unread > 0);
        await logistics.PostAsync("api/notifications/read-all", null);
        Assert.Equal(0, (await logistics.Get<NotificationFeed>("api/notifications")).Unread);

        var sales = await factory.ClientAsync("sales"); // no supply.view: never receives supply alerts
        Assert.DoesNotContain((await sales.Get<NotificationFeed>("api/notifications")).Items, n => n.Kind is "eta" or "overdue");
    }

    [Fact]
    public async Task Data_scope_restricts_every_view_search_and_drill_down()
    {
        var admin = await factory.ClientAsync();
        var create = await admin.PostAsJsonAsync("api/admin/users",
            new UserUpsert("films.buyer", "Films Buyer", null, "Supply Chain", true, ["MANAGEMENT"], "FilmsBuyer2026x", [], ["FILMS"]), ApiFactory.Json);
        Assert.True(create.IsSuccessStatusCode, await create.Content.ReadAsStringAsync());

        var scoped = await factory.ClientAsync("films.buyer", "FilmsBuyer2026x");
        var mine = await scoped.Get<ExecutiveDashboard>("api/executive");
        var all = await admin.Get<ExecutiveDashboard>("api/executive");
        Assert.True(mine.Kpis.First(k => k.Code == "TOTAL_STOCK").Value < all.Kpis.First(k => k.Code == "TOTAL_STOCK").Value);

        var rows = await scoped.Get<PagedResult<InventoryRow>>("api/inventory/rows?pageSize=500");
        Assert.NotEmpty(rows.Items);
        Assert.All(rows.Items, r => Assert.Equal("Films", r.Category));
        Assert.Empty((await scoped.Get<PagedResult<InventoryRow>>("api/inventory/rows?categories=SPAGHETTI")).Items);

        var options = await scoped.Get<FilterOptions>("api/filters/options");
        Assert.Equal(["FILMS"], options.Categories.Select(c => c.Value));

        var search = await scoped.Get<List<SearchResult>>("api/search?q=spaghetti");
        Assert.All(search.Where(r => r.Type == "Product"), r => Assert.StartsWith("FILM", r.Title.Split(" · ")[1]));

        var pasta = (await admin.Get<PagedResult<InventoryRow>>("api/inventory/rows?categories=SPAGHETTI&pageSize=1")).Items[0];
        Assert.Equal(HttpStatusCode.NotFound, (await scoped.GetAsync($"api/products/{pasta.CArtSap}")).StatusCode);

        var export = await scoped.GetAsync("api/export/inventory?format=csv");
        var csv = await export.Content.ReadAsStringAsync();
        Assert.DoesNotContain(pasta.CArtSap, csv);
    }
}

/// <summary>Automated refresh against a fake ERP (a SQLite staging database) and an Excel inbox folder.</summary>
public sealed class RefreshFactory : ApiFactory
{
    public string Inbox { get; } = Path.Combine(Path.GetTempPath(), $"broli-inbox-{Guid.NewGuid():N}");
    public string ErpDb { get; } = Path.Combine(Path.GetTempPath(), $"broli-erp-{Guid.NewGuid():N}.db");

    protected override void Configure(IWebHostBuilder builder)
    {
        builder.UseSetting("DataSources:InboxRoot", Inbox);
        builder.UseSetting("ConnectionStrings:Erp", $"Data Source={ErpDb}");
        builder.UseSetting("DataSources:Connections:Erp:Provider", "Sqlite");
    }

    public void ErpSql(string sql)
    {
        using var c = new SqliteConnection($"Data Source={ErpDb}");
        c.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = sql;
        cmd.ExecuteNonQuery();
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        SqliteConnection.ClearAllPools();
        try { File.Delete(ErpDb); Directory.Delete(Inbox, true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}

public class RefreshApiTests(RefreshFactory factory) : IClassFixture<RefreshFactory>
{
    private static async Task<DataSourceDto> Create(HttpClient c, DataSourceUpsert body)
    {
        var r = await c.PostAsJsonAsync("api/data-sources", body, ApiFactory.Json);
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        return (await r.Content.ReadFromJsonAsync<DataSourceDto>(ApiFactory.Json))!;
    }

    private static async Task<List<DataSourceRunResult>> Run(HttpClient c, int id) =>
        (await (await c.PostAsync($"api/data-sources/{id}/run", null)).Content.ReadFromJsonAsync<List<DataSourceRunResult>>(ApiFactory.Json))!;

    [Fact]
    public async Task Erp_and_inbox_sources_load_valid_data_and_reject_invalid_data()
    {
        var c = await factory.ClientAsync();

        // Unsafe or unknown definitions are refused.
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("api/data-sources",
            new DataSourceUpsert("Bad", "SqlStaging", "inventory", "x; DROP TABLE y", "Erp", null, true), ApiFactory.Json)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("api/data-sources",
            new DataSourceUpsert("Bad", "SqlStaging", "inventory", "V_STOCK", "Unknown", null, true), ApiFactory.Json)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("api/data-sources",
            new DataSourceUpsert("Bad", "ExcelFolder", "inventory", "../etc", null, null, true), ApiFactory.Json)).StatusCode);

        // 1. Supplier master from the ERP staging view → DEMO data purged.
        factory.ErpSql("CREATE TABLE V_SUPPLIERS (Supplier_Code TEXT, Supplier_Name TEXT, Country TEXT); " +
                       "INSERT INTO V_SUPPLIERS VALUES ('SUP-1', 'Anatolia Films', 'TR'), ('SUP-2', 'Black Sea Grain', 'Ukraine');");
        var sup = await Create(c, new DataSourceUpsert("ERP suppliers", "SqlStaging", "supplier-master", "V_SUPPLIERS", "Erp", "05:00", true));
        var r1 = await Run(c, sup.Id);
        Assert.Equal("Imported", r1.Single().Status);
        var status = await c.Get<DataStatus>("api/data/status");
        Assert.False(status.HasDemoData);
        Assert.Equal(2, status.RowCounts["Suppliers"]);

        // 2. Product master dropped as an Excel file in the inbox.
        var folder = Path.Combine(factory.Inbox, "products");
        Directory.CreateDirectory(folder);
        using (var wb = new XLWorkbook())
        {
            var ws = wb.Worksheets.Add("PRODUCT MASTER");
            string[] h = ["CArtSAP", "Description", "Category", "Material Type", "TC Conversion", "Main Supplier"];
            for (var i = 0; i < h.Length; i++) ws.Cell(1, i + 1).Value = h[i];
            ws.Cell(2, 1).Value = "300101"; ws.Cell(2, 2).Value = "FILM RAHMA 500G"; ws.Cell(2, 3).Value = "FILMS"; ws.Cell(2, 4).Value = "Packaging";
            ws.Cell(2, 5).Value = 18000; ws.Cell(2, 6).Value = "SUP-1";
            wb.SaveAs(Path.Combine(folder, "products.xlsx"));
        }
        var prod = await Create(c, new DataSourceUpsert("Inbox products", "ExcelFolder", "product-master", "products", null, null, true));
        Assert.Equal("Imported", (await Run(c, prod.Id)).Single().Status);
        Assert.Empty(Directory.GetFiles(folder, "*.xlsx"));
        Assert.Single(Directory.GetFiles(Path.Combine(folder, "processed"), "*.xlsx"));
        Assert.Equal("No data", (await Run(c, prod.Id)).Single().Status);

        // 3. A stock extract with one bad row is rejected as a whole and reported.
        factory.ErpSql("CREATE TABLE V_STOCK (Date TEXT, CArtSAP TEXT, Stock REAL, Warehouse TEXT); " +
                       "INSERT INTO V_STOCK VALUES ('30/09/2026', '300101', 9000, 'Plant'), ('30/09/2026', 'UNKNOWN', 5, 'Plant');");
        var stock = await Create(c, new DataSourceUpsert("ERP stock", "SqlStaging", "inventory", "V_STOCK", "Erp", "05:30", true));
        var rejected = (await Run(c, stock.Id)).Single();
        Assert.Equal("Rejected", rejected.Status);
        Assert.Equal(1, rejected.Errors);
        Assert.Equal(0, (await c.Get<DataStatus>("api/data/status")).RowCounts["FACT_INVENTORY"]);
        var history = await c.Get<List<ImportBatchDto>>("api/imports/history");
        Assert.Contains(history, b => b.Status == "Rejected" && b.Source == "ERP stock" && b.Message!.Contains("CArtSAP inconnu"));
        var feed = await c.Get<NotificationFeed>("api/notifications");
        Assert.Contains(feed.Items, n => n.Kind == "refresh" && n.Title.Contains("ERP stock"));

        // 4. Corrected at the source → loaded by "refresh all", in master-first order.
        factory.ErpSql("DELETE FROM V_STOCK WHERE CArtSAP = 'UNKNOWN';");
        var all = await (await c.PostAsync("api/data-sources/run-all", null)).Content.ReadFromJsonAsync<List<DataSourceRunResult>>(ApiFactory.Json);
        Assert.NotNull(all);
        Assert.Equal(["ERP suppliers", "Inbox products", "ERP stock"], all.Select(r => r.Source));
        Assert.Equal("Imported", all[^1].Status);
        Assert.Equal(1, (await c.Get<DataStatus>("api/data/status")).RowCounts["FACT_INVENTORY"]);

        var sources = await c.Get<List<DataSourceDto>>("api/data-sources");
        Assert.All(sources, s => Assert.NotNull(s.LastRunUtc));
    }
}

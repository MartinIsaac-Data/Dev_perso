using System.Net;
using System.Net.Http.Json;
using Broli.SOP.Contracts.Dtos;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;

namespace Broli.SOP.Tests;

/// <summary>Runs only when BROLI_TEST_SQLSERVER is set (the SQL Server job of the CI); skipped otherwise.</summary>
public sealed class SqlServerFactAttribute : FactAttribute
{
    public SqlServerFactAttribute()
    {
        if (ApiFactory.SqlServer is null) Skip = "Needs SQL Server: set BROLI_TEST_SQLSERVER";
    }
}

public sealed class NoMigrationFactory : ApiFactory
{
    protected override void Configure(IWebHostBuilder builder) => builder.UseSetting("Database:ApplyMigrations", "false");
}

public class DeploymentTests
{
    [SqlServerFact]
    public void Api_refuses_to_start_on_a_schema_the_DBA_has_not_migrated()
    {
        using var factory = new NoMigrationFactory();
        var ex = Assert.ThrowsAny<Exception>(() => factory.CreateClient());
        var inner = ex;
        while (inner is not InvalidOperationException && inner.InnerException is not null) inner = inner.InnerException;
        Assert.Contains("not up to date", inner.Message);
        Assert.Contains("sql/migrations.sql", inner.Message);
    }
}

/// <summary>Makes every request arrive from a fixed address, as the web server (loopback) or an untrusted machine would.</summary>
public class RemoteAddressFactory(string remote) : ApiFactory
{
    protected override void Configure(IWebHostBuilder builder) =>
        builder.ConfigureServices(s => s.AddSingleton<IStartupFilter>(new RemoteAddressFilter(IPAddress.Parse(remote))));

    private sealed class RemoteAddressFilter(IPAddress address) : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
        {
            app.Use((ctx, nextMiddleware) => { ctx.Connection.RemoteIpAddress = address; return nextMiddleware(ctx); });
            next(app);
        };
    }
}

public sealed class WebServerFactory() : RemoteAddressFactory("127.0.0.1");
public sealed class UntrustedFactory() : RemoteAddressFactory("10.1.2.3");

public class LoginRateLimitTests(WebServerFactory webServer, UntrustedFactory untrusted)
    : IClassFixture<WebServerFactory>, IClassFixture<UntrustedFactory>
{
    private static async Task<int> TooManyAsync(HttpClient client, Func<int, string> forwardedFor, int attempts = 25)
    {
        var rejected = 0;
        for (var i = 0; i < attempts; i++)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, "api/auth/login")
            {
                Content = JsonContent.Create(new LoginRequest($"nobody{i}", "wrong-password")),
            };
            request.Headers.Add("X-Forwarded-For", forwardedFor(i));
            using var response = await client.SendAsync(request);
            if (response.StatusCode == HttpStatusCode.TooManyRequests) rejected++;
        }
        return rejected;
    }

    [Fact]
    public async Task Users_behind_the_web_server_each_have_their_own_login_limit()
    {
        Assert.Equal(0, await TooManyAsync(webServer.CreateClient(), i => $"192.168.10.{i + 1}"));
    }

    [Fact]
    public async Task One_machine_is_still_limited()
    {
        Assert.True(await TooManyAsync(webServer.CreateClient(), _ => "192.168.20.7") > 0);
    }

    [Fact]
    public async Task A_forwarded_address_from_an_untrusted_machine_is_ignored()
    {
        Assert.True(await TooManyAsync(untrusted.CreateClient(), i => $"192.168.30.{i + 1}") > 0);
    }
}

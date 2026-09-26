using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;

namespace Broli.SOP.LoadTest;

/// <summary>
/// Simulates concurrent users browsing the portal through the REST API (the Blazor server makes the same calls).
/// Each virtual user repeats a realistic journey with random filters and a "think time" between screens.
/// </summary>
public static class Load
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static async Task<int> RunAsync(string api, string user, string password, int users, int seconds, int thinkMs, string report)
    {
        using var handler = new SocketsHttpHandler { MaxConnectionsPerServer = 512, PooledConnectionLifetime = TimeSpan.FromMinutes(5) };
        using var http = new HttpClient(handler) { BaseAddress = new Uri(api), Timeout = TimeSpan.FromSeconds(120) };

        var login = await http.PostAsJsonAsync("api/auth/login", new LoginRequest(user, password));
        login.EnsureSuccessStatusCode();
        var token = (await login.Content.ReadFromJsonAsync<LoginResponse>(Json))!.Token;
        http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);

        var options = (await http.GetFromJsonAsync<FilterOptions>("api/filters/options", Json))!;
        var skus = (await http.GetFromJsonAsync<PagedResult<InventoryRow>>("api/inventory/rows?pageSize=500", Json))!.Items.Select(r => r.CArtSap).ToArray();
        Console.WriteLine($"Target {api}: {options.Categories.Count} families, {options.Brands.Count} brands, sample of {skus.Length} SKUs");

        var samples = new ConcurrentBag<(string Endpoint, double Ms, bool Ok)>();
        var until = DateTime.UtcNow.AddSeconds(seconds);
        var clock = Stopwatch.StartNew();

        async Task Hit(string name, string url)
        {
            var sw = Stopwatch.StartNew();
            var ok = false;
            try
            {
                using var r = await http.GetAsync(url);
                await r.Content.ReadAsByteArrayAsync();
                ok = r.IsSuccessStatusCode;
            }
            catch (Exception) { ok = false; }
            samples.Add((name, sw.Elapsed.TotalMilliseconds, ok));
        }

        async Task VirtualUser(int id)
        {
            var rnd = new Random(id * 7919);
            string Filter()
            {
                var x = rnd.NextDouble();
                var cat = options.Categories[rnd.Next(options.Categories.Count)].Value;
                var brand = options.Brands[rnd.Next(options.Brands.Count)].Value;
                return x switch
                {
                    < 0.35 => "",
                    < 0.65 => $"categories={Uri.EscapeDataString(cat)}",
                    < 0.85 => $"categories={Uri.EscapeDataString(cat)}&brands={Uri.EscapeDataString(brand)}",
                    _ => $"months={rnd.Next(1, 13)}",
                };
            }
            async Task Think() => await Task.Delay(thinkMs == 0 ? 0 : rnd.Next(thinkMs / 2, thinkMs * 3 / 2));

            while (DateTime.UtcNow < until)
            {
                var f = Filter();
                await Hit("executive", $"api/executive?{f}"); await Think();
                await Hit("inventory", $"api/inventory?{f}");
                await Hit("inventory rows", $"api/inventory/rows?{f}&view=at-risk"); await Think();
                await Hit("product", $"api/products/{skus[rnd.Next(skus.Length)]}?{f}"); await Think();
                switch (rnd.Next(7))
                {
                    case 0: await Hit("demand", $"api/demand?{f}"); await Hit("demand rows", $"api/demand/rows?{f}"); break;
                    case 1: await Hit("supply", $"api/supply?{f}"); await Hit("supply rows", $"api/supply/rows?{f}&view=late"); break;
                    case 2: await Hit("mrp", $"api/mrp?{f}"); await Hit("mrp rows", $"api/mrp/rows?{f}"); break;
                    case 3: await Hit("materials", $"api/materials/{(rnd.Next(2) == 0 ? "films" : "raw-materials")}?{f}"); break;
                    case 4: await Hit("transit", $"api/transit?{f}"); await Hit("suppliers", $"api/suppliers?{f}"); break;
                    case 5: await Hit("risks", $"api/risks?{f}"); break;
                    default: await Hit("meeting", $"api/meeting?{f}"); await Hit("actions", "api/actions?view=active"); break;
                }
                await Think();
                await Hit("search", $"api/search?q={Uri.EscapeDataString("item " + rnd.Next(100, 999))}");
                await Hit("notifications", "api/notifications"); await Think();
            }
        }

        await Task.WhenAll(Enumerable.Range(1, users).Select(VirtualUser));
        var elapsed = clock.Elapsed.TotalSeconds;

        var all = samples.ToList();
        var sb = new StringBuilder();
        sb.AppendLine($"| Endpoint | Requests | Errors | p50 ms | p95 ms | p99 ms | Max ms |");
        sb.AppendLine("|---|---:|---:|---:|---:|---:|---:|");
        foreach (var g in all.GroupBy(s => s.Endpoint).OrderBy(g => g.Key))
            sb.AppendLine(Line(g.Key, g.ToList()));
        sb.AppendLine(Line("**All**", all));
        var summary = $"{users} users, {seconds} s, think time {thinkMs} ms: {all.Count:N0} requests, {all.Count / elapsed:0.0} req/s, {all.Count(s => !s.Ok)} errors";
        Console.WriteLine(summary);
        Console.WriteLine(sb);
        File.AppendAllText(report, $"### {summary}\n\n{sb}\n");
        return all.Any(s => !s.Ok) ? 1 : 0;
    }

    private static string Line(string name, List<(string Endpoint, double Ms, bool Ok)> s)
    {
        var ms = s.Select(x => x.Ms).Order().ToList();
        double P(double q) => ms.Count == 0 ? 0 : ms[Math.Min(ms.Count - 1, (int)Math.Ceiling(q * ms.Count) - 1)];
        return $"| {name} | {s.Count:N0} | {s.Count(x => !x.Ok)} | {P(.5):0} | {P(.95):0} | {P(.99):0} | {ms.LastOrDefault():0} |";
    }
}

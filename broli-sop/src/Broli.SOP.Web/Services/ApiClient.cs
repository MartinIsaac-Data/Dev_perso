using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Broli.SOP.Contracts;
using Broli.SOP.Contracts.Dtos;
using Microsoft.AspNetCore.Components;

namespace Broli.SOP.Web.Services;

public sealed class ApiException(string message, IReadOnlyList<string>? details = null, HttpStatusCode status = HttpStatusCode.BadRequest) : Exception(message)
{
    public IReadOnlyList<string> Details { get; } = details ?? [];
    public HttpStatusCode Status { get; } = status;
    public string Full => Details.Count == 0 ? Message : $"{Message} {string.Join(" ", Details)}";
}

/// <summary>
/// The only way the UI reaches data: typed calls to the REST API. The UI never touches
/// Excel files or the database, so the data source can change without touching pages.
/// </summary>
public sealed class ApiClient(HttpClient http, AuthSession session, NavigationManager nav, ILogger<ApiClient> logger)
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { Converters = { new JsonStringEnumConverter() } };

    public Task<T> GetAsync<T>(string path, SopFilter? filter = null, TableQuery? query = null, CancellationToken ct = default) =>
        SendAsync<T>(HttpMethod.Get, Url(path, filter, query), null, ct);

    public Task<T> PostAsync<T>(string path, object? body, CancellationToken ct = default) => SendAsync<T>(HttpMethod.Post, path, body, ct);
    public Task<T> PutAsync<T>(string path, object? body, CancellationToken ct = default) => SendAsync<T>(HttpMethod.Put, path, body, ct);
    public Task SendAsync(HttpMethod method, string path, object? body = null, CancellationToken ct = default) => SendAsync<object?>(method, path, body, ct);

    public async Task<(byte[] Content, string FileName)> DownloadAsync(string path, SopFilter? filter = null, TableQuery? query = null,
        string? extra = null, CancellationToken ct = default)
    {
        var url = Url(path, filter, query);
        if (extra is not null) url += (url.Contains('?') ? "&" : "?") + extra;
        using var response = await RawAsync(new HttpRequestMessage(HttpMethod.Get, url), ct);
        var name = response.Content.Headers.ContentDisposition?.FileNameStar ?? response.Content.Headers.ContentDisposition?.FileName ?? "export";
        return (await response.Content.ReadAsByteArrayAsync(ct), name.Trim('"'));
    }

    public async Task<T> UploadAsync<T>(string path, Stream content, string fileName, CancellationToken ct = default)
    {
        using var form = new MultipartFormDataContent();
        var file = new StreamContent(content);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        form.Add(file, "file", fileName);
        using var response = await RawAsync(new HttpRequestMessage(HttpMethod.Post, path) { Content = form }, ct);
        return (await response.Content.ReadFromJsonAsync<T>(Json, ct))!;
    }

    public async Task<LoginResponse?> LoginAsync(LoginRequest request, CancellationToken ct = default)
    {
        using var response = await http.PostAsJsonAsync("api/auth/login", request, Json, ct);
        if (response.StatusCode == HttpStatusCode.Unauthorized) return null;
        if (response.StatusCode == HttpStatusCode.TooManyRequests) throw new ApiException("Too many attempts. Wait a minute and try again.");
        await EnsureSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<LoginResponse>(Json, ct);
    }

    private async Task<T> SendAsync<T>(HttpMethod method, string url, object? body, CancellationToken ct)
    {
        var request = new HttpRequestMessage(method, url);
        if (body is not null) request.Content = JsonContent.Create(body, body.GetType(), options: Json);
        using var response = await RawAsync(request, ct);
        if (response.StatusCode == HttpStatusCode.NoContent || typeof(T) == typeof(object)) return default!;
        return (await response.Content.ReadFromJsonAsync<T>(Json, ct))!;
    }

    private async Task<HttpResponseMessage> RawAsync(HttpRequestMessage request, CancellationToken ct)
    {
        if (session.Token is { } token) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        HttpResponseMessage response;
        try
        {
            response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        }
        catch (HttpRequestException ex)
        {
            logger.LogError(ex, "API unreachable: {Url}", request.RequestUri);
            throw new ApiException("The S&OP service is unreachable. Try again in a moment.", status: HttpStatusCode.ServiceUnavailable);
        }
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            response.Dispose();
            await session.SignOutAsync();
            nav.NavigateTo("/login?expired=1", forceLoad: false);
            throw new ApiException("Your session has expired. Please sign in again.", status: HttpStatusCode.Unauthorized);
        }
        await EnsureSuccess(response, ct);
        return response;
    }

    private static async Task EnsureSuccess(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        ApiError? error = null;
        try { error = await response.Content.ReadFromJsonAsync<ApiError>(Json, ct); } catch (Exception) { /* not a JSON error body */ }
        var status = response.StatusCode;
        response.Dispose();
        throw status switch
        {
            HttpStatusCode.Forbidden => new ApiException("You do not have permission for this action.", status: status),
            HttpStatusCode.NotFound => new ApiException(error?.Message ?? "Not found.", status: status),
            _ => new ApiException(error?.Message ?? $"Request failed ({(int)status}).", error?.Details, status),
        };
    }

    private static string Url(string path, SopFilter? filter, TableQuery? query)
    {
        var parts = new[] { filter?.ToQueryString(), query?.ToQueryString() }.Where(p => !string.IsNullOrEmpty(p));
        var qs = string.Join('&', parts);
        return qs.Length == 0 ? path : $"{path}{(path.Contains('?') ? "&" : "?")}{qs}";
    }
}

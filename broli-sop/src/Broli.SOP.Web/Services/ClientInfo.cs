namespace Broli.SOP.Web.Services;

/// <summary>
/// The browser's address for this circuit, forwarded to the API (X-Forwarded-For) so the login limit and logs see the
/// real user machine rather than the web server. Set once by <c>Routes</c> from the page request.
/// </summary>
public sealed class ClientInfo
{
    public string? RemoteIp { get; set; }
}

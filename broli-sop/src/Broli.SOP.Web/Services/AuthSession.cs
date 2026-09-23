using Broli.SOP.Contracts.Dtos;
using Microsoft.AspNetCore.Components.Server.ProtectedBrowserStorage;

namespace Broli.SOP.Web.Services;

/// <summary>
/// The signed-in user for this browser tab (one Blazor circuit). The API token is kept server-side
/// in the circuit and mirrored to encrypted session storage so a page refresh keeps the session.
/// </summary>
public sealed class AuthSession(ProtectedSessionStorage storage, ILogger<AuthSession> logger)
{
    private const string Key = "sop.session";
    private sealed record Stored(string Token, DateTime ExpiresAtUtc, UserInfo User);

    public string? Token { get; private set; }
    public UserInfo? User { get; private set; }
    public DateTime ExpiresAtUtc { get; private set; }
    public bool Restored { get; private set; }
    public bool IsAuthenticated => Token is not null && ExpiresAtUtc > DateTime.UtcNow;

    public event Action? Changed;

    public bool Can(string permission) => User?.Permissions.Contains(permission) == true;

    public async Task RestoreAsync()
    {
        if (Restored) return;
        try
        {
            var result = await storage.GetAsync<Stored>(Key);
            if (result is { Success: true, Value: { } s } && s.ExpiresAtUtc > DateTime.UtcNow)
            {
                Token = s.Token;
                ExpiresAtUtc = s.ExpiresAtUtc;
                User = s.User;
            }
        }
        catch (Exception ex)
        {
            // Storage written with an older key ring or tampered with: start a fresh session.
            logger.LogDebug(ex, "Could not restore the session");
        }
        Restored = true;
        Changed?.Invoke();
    }

    public async Task SignInAsync(LoginResponse response)
    {
        Token = response.Token;
        ExpiresAtUtc = response.ExpiresAtUtc;
        User = response.User;
        Restored = true;
        await storage.SetAsync(Key, new Stored(response.Token, response.ExpiresAtUtc, response.User));
        Changed?.Invoke();
    }

    public async Task SignOutAsync()
    {
        Token = null;
        User = null;
        try { await storage.DeleteAsync(Key); } catch (Exception ex) { logger.LogDebug(ex, "Session storage not available"); }
        Changed?.Invoke();
    }
}

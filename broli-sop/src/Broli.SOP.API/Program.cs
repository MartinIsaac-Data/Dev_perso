using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;
using Broli.SOP.API.Infrastructure;
using Broli.SOP.Application;
using Broli.SOP.Application.Abstractions;
using Broli.SOP.Data;
using Broli.SOP.Data.Seeding;
using Broli.SOP.Infrastructure;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

// ---- JWT signing key: configuration only (Jwt__Key). Development falls back to an ephemeral random key.
var jwt = builder.Configuration.GetSection(JwtOptions.Section).Get<JwtOptions>() ?? new JwtOptions();
if (string.IsNullOrWhiteSpace(jwt.Key))
{
    if (!builder.Environment.IsDevelopment() && !builder.Environment.IsEnvironment("Testing"))
        throw new InvalidOperationException("Jwt:Key must be configured (environment variable Jwt__Key, at least 32 characters).");
    jwt.Key = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48));
}
if (jwt.Key.Length < 32) throw new InvalidOperationException("Jwt:Key must be at least 32 characters.");

builder.Services
    .AddSopApplication()
    .AddSopData(builder.Configuration)
    .AddSopInfrastructure(jwt);

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<ICurrentUser, HttpCurrentUser>();
builder.Services.AddSingleton<RefreshScheduler>();
builder.Services.AddHostedService(sp => sp.GetRequiredService<RefreshScheduler>());

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.MapInboundClaims = false;
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = jwt.Issuer,
            ValidateAudience = true,
            ValidAudience = jwt.Audience,
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwt.Key)),
            ValidateLifetime = true,
            ClockSkew = TimeSpan.FromMinutes(1),
            NameClaimType = System.Security.Claims.ClaimTypes.Name,
            RoleClaimType = System.Security.Claims.ClaimTypes.Role,
        };
    });
builder.Services.AddAuthorization(o => o.AddPermissionPolicies());

builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    o.AddPolicy("login", ctx => RateLimitPartition.GetFixedWindowLimiter(
        ctx.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = 20, Window = TimeSpan.FromMinutes(1) }));
});

builder.Services.AddControllers()
    .AddJsonOptions(o => o.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter()));
builder.Services.AddExceptionHandler<ApiExceptionHandler>();
builder.Services.AddProblemDetails();
builder.Services.AddResponseCompression(o => o.EnableForHttps = true);
builder.Services.AddOpenApi();
builder.Services.AddHealthChecks();

var app = builder.Build();

using (var scope = app.Services.CreateScope())
    await scope.ServiceProvider.GetRequiredService<DatabaseInitializer>().InitializeAsync();

app.UseExceptionHandler();
if (!app.Environment.IsDevelopment() && !app.Environment.IsEnvironment("Testing"))
{
    app.UseHsts();
    app.UseHttpsRedirection();
}
app.Use(async (ctx, next) =>
{
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["X-Frame-Options"] = "DENY";
    ctx.Response.Headers["Referrer-Policy"] = "no-referrer";
    await next();
});
app.UseResponseCompression();
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();

if (app.Environment.IsDevelopment()) app.MapOpenApi().AllowAnonymous();
app.MapHealthChecks("/health").AllowAnonymous();
app.MapControllers();

app.Run();

/// <summary>Exposed for integration tests (WebApplicationFactory).</summary>
public partial class Program;

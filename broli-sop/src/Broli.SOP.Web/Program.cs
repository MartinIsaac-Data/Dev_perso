using Broli.SOP.Web.Components;
using Broli.SOP.Web.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents(o => o.DetailedErrors = builder.Environment.IsDevelopment());

// The UI only talks to the REST API. Api:BaseUrl points at Broli.SOP.API.
var apiBase = builder.Configuration["Api:BaseUrl"] ?? "http://localhost:5080/";
builder.Services.AddHttpClient<ApiClient>(c =>
{
    c.BaseAddress = new Uri(apiBase.EndsWith('/') ? apiBase : apiBase + "/");
    c.Timeout = TimeSpan.FromSeconds(100);
});
builder.Services.AddScoped<ClientInfo>();
builder.Services.AddScoped<AuthSession>();
builder.Services.AddScoped<FilterState>();
builder.Services.AddScoped<UiState>();

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
    app.UseHttpsRedirection();
}
app.Use(async (ctx, next) =>
{
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["X-Frame-Options"] = "SAMEORIGIN";
    ctx.Response.Headers["Referrer-Policy"] = "same-origin";
    await next();
});
app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);
app.UseAntiforgery();

app.MapStaticAssets();
app.MapRazorComponents<App>().AddInteractiveServerRenderMode();

app.Run();

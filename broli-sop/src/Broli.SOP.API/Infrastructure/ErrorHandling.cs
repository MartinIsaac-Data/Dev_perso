using Broli.SOP.Application.Services;
using Broli.SOP.Contracts.Dtos;
using Microsoft.AspNetCore.Diagnostics;

namespace Broli.SOP.API.Infrastructure;

/// <summary>Maps business validation to 400 and hides internals of unexpected errors behind a trace id.</summary>
public sealed class ApiExceptionHandler(ILogger<ApiExceptionHandler> logger) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext context, Exception exception, CancellationToken ct)
    {
        switch (exception)
        {
            case ValidationException v:
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                await context.Response.WriteAsJsonAsync(new ApiError("Validation failed.", v.Errors), ct);
                return true;
            case ArgumentException a:
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                await context.Response.WriteAsJsonAsync(new ApiError(a.Message), ct);
                return true;
            case OperationCanceledException when context.RequestAborted.IsCancellationRequested:
                context.Response.StatusCode = 499;
                return true;
            default:
                logger.LogError(exception, "Unhandled error on {Method} {Path} ({TraceId})", context.Request.Method, context.Request.Path, context.TraceIdentifier);
                context.Response.StatusCode = StatusCodes.Status500InternalServerError;
                await context.Response.WriteAsJsonAsync(new ApiError($"An unexpected error occurred. Reference: {context.TraceIdentifier}"), ct);
                return true;
        }
    }
}

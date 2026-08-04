using System.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Options;
using Instrumentation.Constants;
using Instrumentation.Logging;
using Instrumentation.Metrics;
using Instrumentation.Models;
using Instrumentation.Options;

namespace Instrumentation.Middleware;

public sealed class InstrumentationMiddleware : IMiddleware
{
    private readonly RequestStats _requestStats;
    private readonly RequestFaultContext _requestFaultContext;
    private readonly LogWriter _logWriter;
    private readonly InstrumentationOptions _options;

    public InstrumentationMiddleware(
        RequestStats requestStats,
        RequestFaultContext requestFaultContext,
        LogWriter logWriter,
        IOptions<InstrumentationOptions> options)
    {
        _requestStats = requestStats;
        _requestFaultContext = requestFaultContext;
        _logWriter = logWriter;
        _options = options.Value;
    }

    public async Task InvokeAsync(
        HttpContext context,
        RequestDelegate next)
    {
        if (context.Request.Path.StartsWithSegments("/admin"))
        {
            await next(context);
            return;
        }

        var traceId = GetOrCreateTraceId(context);


        context.Response.Headers[InstrumentationConstants.TraceIdHeader] =
            traceId;

        context.Items[InstrumentationConstants.RequestContextKey] =
            new RequestContext
            {
                TraceId = traceId
            };

        var stopwatch = Stopwatch.StartNew();
        var success = false;

        try
        {
            await next(context);
            success = context.Response.StatusCode < 500;
        }
        catch (Exception ex)
        {
            await WriteFailureLogAsync(
                context,
                traceId,
                stopwatch.Elapsed.TotalMilliseconds,
                ex.Message);

            throw;
        }
        finally
        {
            stopwatch.Stop();

            _requestStats.Record(
                success,
                stopwatch.Elapsed.TotalMilliseconds);

            if (!success || context.Response.StatusCode >= 400)
            {
                await WriteFailureLogAsync(
                    context,
                    traceId,
                    stopwatch.Elapsed.TotalMilliseconds,
                    "HTTP request returned an error response");
            }
            else
            {
                await _logWriter.WriteAsync(
                    LogLevels.Information,
                    LogEvents.RequestHandled,
                    traceId,
                    "Request handled successfully",
                    new
                    {
                        handler = GetHandler(context),
                        version = GetServiceVersion(),
                        method = context.Request.Method,
                        path = context.Request.Path.Value,
                        status_code = context.Response.StatusCode,
                        latency_ms = stopwatch.Elapsed.TotalMilliseconds
                    });
            }
        }
    }

    private async Task WriteFailureLogAsync(
        HttpContext context,
        string traceId,
        double latencyMs,
        string fallbackMessage)
    {
        var statusCode = context.Response.StatusCode >= 400
            ? context.Response.StatusCode
            : StatusCodes.Status500InternalServerError;

        var logContext = new Dictionary<string, object?>(
            _requestFaultContext.Properties)
        {
            ["handler"] = GetHandler(context),
            ["version"] = GetServiceVersion(),
            ["path"] = context.Request.Path.Value,
            ["method"] = context.Request.Method,
            ["status_code"] = statusCode,
            ["latency_ms"] = latencyMs
        };

        await _logWriter.WriteAsync(
            _requestFaultContext.Level ?? LogLevels.Error,
            _requestFaultContext.Event ?? LogEvents.HttpRequestFailed,
            traceId,
            _requestFaultContext.Message ?? fallbackMessage,
            logContext);
    }

    private string? GetServiceVersion() =>
        _options.ServiceVersionProvider?.Invoke();

    private static string GetHandler(HttpContext context)
    {
        return context.Request.RouteValues.TryGetValue(
            "action",
            out var action) &&
            action is not null
            ? ToSnakeCase(action.ToString()!)
            : "unknown";
    }

    private static string ToSnakeCase(string value) =>
        string.Concat(value.Select((character, index) =>
            index > 0 && char.IsUpper(character)
                ? $"_{char.ToLowerInvariant(character)}"
                : char.ToLowerInvariant(character).ToString()));

    private static string GetOrCreateTraceId(HttpContext context)
    {
        if (context.Request.Headers.TryGetValue(
                InstrumentationConstants.TraceIdHeader,
                out var values))
        {
            return values.ToString();
        }

        return Guid.NewGuid().ToString("N");
    }
}
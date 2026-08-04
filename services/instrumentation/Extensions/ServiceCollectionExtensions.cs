using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using Instrumentation.Logging;
using Instrumentation.Middleware;
using Instrumentation.Metrics;
using Instrumentation.Options;
using Instrumentation.Tracing;
using Instrumentation.Models;

namespace Instrumentation.Extensions;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddPlatformInstrumentation(
        this IServiceCollection services,
        string connectionString,
        Action<InstrumentationOptions> configure)
    {
        services.Configure(configure);

        services.AddSingleton(
            new NpgsqlDataSourceBuilder(connectionString).Build());

        services.AddSingleton<RequestStats>();
        services.AddSingleton<LogWriter>();
        services.AddSingleton<DbConnectionTracker>();

        services.AddHttpContextAccessor();
        services.AddTransient<InstrumentationMiddleware>();
        services.AddTransient<TraceIdPropagationHandler>();
        services.AddScoped<RequestFaultContext>();

        return services;
    }
    public static IApplicationBuilder UsePlatformInstrumentation(
        this IApplicationBuilder app)
    {
        app.UseMiddleware<InstrumentationMiddleware>();

        return app;
    }
}
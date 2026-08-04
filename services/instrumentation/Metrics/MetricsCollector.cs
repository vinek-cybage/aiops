using System.Diagnostics;
using Dapper;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using Npgsql;
using Instrumentation.Options;

namespace Instrumentation.Metrics;

public sealed class MetricsCollector(
    NpgsqlDataSource dataSource,
    RequestStats requestStats,
    DbConnectionTracker tracker,
    IOptions<InstrumentationOptions> options)
    : BackgroundService
{
    private readonly NpgsqlDataSource _dataSource = dataSource;
    private readonly RequestStats _requestStats = requestStats;
    private readonly DbConnectionTracker _tracker = tracker;
    private readonly InstrumentationOptions _options = options.Value;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(_options.MetricsFlushInterval, stoppingToken);

            var snapshot = _requestStats.TakeSnapshotAndReset();

            var sql =
                """
                INSERT INTO metrics
                (
                    ts,
                    service,
                    error_rate,
                    p99_latency_ms,
                    active_connections,
                    rss_mb
                )
                VALUES
                (
                    @Ts,
                    @Service,
                    @ErrorRate,
                    @P99Latency,
                    @ActiveConnections,
                    @RssMb
                );
                """;

            await using var connection =
                await _dataSource.OpenConnectionAsync(stoppingToken);

            await connection.ExecuteAsync(
                sql,
                new
                {
                    Ts = DateTime.UtcNow,
                    Service = _options.ServiceName,
                    ErrorRate = snapshot.ErrorRate,
                    P99Latency = snapshot.P99LatencyMs,
                    ActiveConnections = _tracker.ActiveConnections,
                    RssMb = Process.GetCurrentProcess().WorkingSet64 / 1024d / 1024d
                });
        }
    }
}
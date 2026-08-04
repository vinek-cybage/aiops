using System.Text.Json;
using Dapper;
using Microsoft.Extensions.Options;
using Npgsql;
using Instrumentation.Options;
using Instrumentation.Serialization;

namespace Instrumentation.Logging;

public sealed class LogWriter(
    NpgsqlDataSource dataSource,
    IOptions<InstrumentationOptions> options)
{
    private readonly NpgsqlDataSource _dataSource = dataSource;
    private readonly InstrumentationOptions _options = options.Value;

    public async Task WriteAsync<TContext>(
        string level,
        string @event,
        string? traceId,
        string message,
        TContext? context = default,
        CancellationToken cancellationToken = default)
    {
        await using var connection =
            await _dataSource.OpenConnectionAsync(cancellationToken);

        var sql =
            """
            INSERT INTO logs
            (
                ts,
                service,
                level,
                event,
                trace_id,
                message,
                context
            )
            VALUES
            (
                @Ts,
                @Service,
                @Level,
                @Event,
                @TraceId,
                @Message,
                CAST(@Context AS jsonb)
            );
            """;

        var parameters = new
        {
            Ts = DateTime.UtcNow,
            Service = _options.ServiceName,
            Level = level,
            Event = @event,
            TraceId = traceId,
            Message = message,
            Context = context is null
                ? null
                : JsonSerializer.Serialize(context, JsonDefaults.Options)
        };

        await connection.ExecuteAsync(
            new CommandDefinition(
                sql,
                parameters,
                cancellationToken: cancellationToken));
    }
}
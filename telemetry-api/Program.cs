using System.Text.Json;
using Npgsql;
using NpgsqlTypes;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader()));

var app = builder.Build();
app.UseCors();

var connString = Environment.GetEnvironmentVariable("DATABASE_URL")
    ?? "Host=aiops-db;Port=5432;Username=aiops;Password=aiops;Database=aiops";

async Task<NpgsqlConnection> OpenConnAsync()
{
    var conn = new NpgsqlConnection(connString);
    await conn.OpenAsync();
    return conn;
}

async Task InitDbAsync()
{
    const int maxAttempts = 10;
    for (var attempt = 1; attempt <= maxAttempts; attempt++)
    {
        try
        {
            await using var conn = await OpenConnAsync();
            await using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                CREATE TABLE IF NOT EXISTS telemetry_logs (
                    id       SERIAL PRIMARY KEY,
                    ts       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    level    TEXT NOT NULL,
                    service  TEXT NOT NULL,
                    message  TEXT NOT NULL,
                    trace_id TEXT
                );
                CREATE TABLE IF NOT EXISTS telemetry_traces (
                    id          SERIAL PRIMARY KEY,
                    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    trace_id    TEXT NOT NULL,
                    service     TEXT NOT NULL,
                    span_name   TEXT NOT NULL,
                    duration_ms DOUBLE PRECISION NOT NULL,
                    is_error    BOOLEAN NOT NULL DEFAULT FALSE,
                    attributes  JSONB
                );
                CREATE TABLE IF NOT EXISTS telemetry_metrics (
                    id    SERIAL PRIMARY KEY,
                    ts    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    name  TEXT NOT NULL,
                    value DOUBLE PRECISION NOT NULL,
                    tags  JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_logs_trace_id ON telemetry_logs (trace_id);
                CREATE INDEX IF NOT EXISTS idx_telemetry_traces_trace_id ON telemetry_traces (trace_id);
                CREATE INDEX IF NOT EXISTS idx_telemetry_metrics_name ON telemetry_metrics (name);
                """;
            await cmd.ExecuteNonQueryAsync();
            app.Logger.LogInformation("DB ready");
            return;
        }
        catch (Exception ex) when (attempt < maxAttempts)
        {
            app.Logger.LogWarning("DB not ready ({Attempt}/{Max}): {Message}", attempt, maxAttempts, ex.Message);
            await Task.Delay(2000);
        }
    }
    throw new InvalidOperationException("DB unavailable after 10 attempts");
}

NpgsqlParameter JsonbParam(string name, object? value) => new(name, NpgsqlDbType.Jsonb)
{
    Value = value is null ? DBNull.Value : JsonSerializer.Serialize(value)
};

await InitDbAsync();

app.MapGet("/api/health", () => Results.Ok(new { status = "ok" }));

app.MapPost("/api/logs", async (LogEntry[] entries) =>
{
    await using var conn = await OpenConnAsync();
    foreach (var e in entries)
    {
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = "INSERT INTO telemetry_logs (level, service, message, trace_id) VALUES (@level, @service, @message, @trace_id)";
        cmd.Parameters.AddWithValue("level", e.Level);
        cmd.Parameters.AddWithValue("service", e.Service);
        cmd.Parameters.AddWithValue("message", e.Message);
        cmd.Parameters.AddWithValue("trace_id", (object?)e.TraceId ?? DBNull.Value);
        await cmd.ExecuteNonQueryAsync();
    }
    return Results.Accepted(value: new { inserted = entries.Length });
});

app.MapGet("/api/logs", async (string? service, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, level, service, message, trace_id FROM telemetry_logs WHERE @service IS NULL OR service = @service ORDER BY ts DESC LIMIT @limit";
    cmd.Parameters.AddWithValue("service", (object?)service ?? DBNull.Value);
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt32(0),
            ts = reader.GetDateTime(1),
            level = reader.GetString(2),
            service = reader.GetString(3),
            message = reader.GetString(4),
            trace_id = reader.IsDBNull(5) ? null : reader.GetString(5),
        });
    }
    return Results.Ok(results);
});

app.MapPost("/api/traces", async (TraceSpan[] spans) =>
{
    await using var conn = await OpenConnAsync();
    foreach (var s in spans)
    {
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = "INSERT INTO telemetry_traces (trace_id, service, span_name, duration_ms, is_error, attributes) VALUES (@trace_id, @service, @span_name, @duration_ms, @is_error, @attributes)";
        cmd.Parameters.AddWithValue("trace_id", s.TraceId);
        cmd.Parameters.AddWithValue("service", s.Service);
        cmd.Parameters.AddWithValue("span_name", s.SpanName);
        cmd.Parameters.AddWithValue("duration_ms", s.DurationMs);
        cmd.Parameters.AddWithValue("is_error", s.IsError);
        cmd.Parameters.Add(JsonbParam("attributes", s.Attributes));
        await cmd.ExecuteNonQueryAsync();
    }
    return Results.Accepted(value: new { inserted = spans.Length });
});

app.MapGet("/api/traces/{traceId}", async (string traceId) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, service, span_name, duration_ms, is_error, attributes FROM telemetry_traces WHERE trace_id = @trace_id ORDER BY ts";
    cmd.Parameters.AddWithValue("trace_id", traceId);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt32(0),
            ts = reader.GetDateTime(1),
            service = reader.GetString(2),
            span_name = reader.GetString(3),
            duration_ms = reader.GetDouble(4),
            is_error = reader.GetBoolean(5),
            attributes = reader.IsDBNull(6) ? null : JsonDocument.Parse(reader.GetString(6)).RootElement,
        });
    }
    return Results.Ok(results);
});

app.MapPost("/api/metrics", async (MetricPoint[] points) =>
{
    await using var conn = await OpenConnAsync();
    foreach (var m in points)
    {
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = "INSERT INTO telemetry_metrics (name, value, tags) VALUES (@name, @value, @tags)";
        cmd.Parameters.AddWithValue("name", m.Name);
        cmd.Parameters.AddWithValue("value", m.Value);
        cmd.Parameters.Add(JsonbParam("tags", m.Tags));
        await cmd.ExecuteNonQueryAsync();
    }
    return Results.Accepted(value: new { inserted = points.Length });
});

app.MapGet("/api/metrics", async (string? name, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, name, value, tags FROM telemetry_metrics WHERE @name IS NULL OR name = @name ORDER BY ts DESC LIMIT @limit";
    cmd.Parameters.AddWithValue("name", (object?)name ?? DBNull.Value);
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt32(0),
            ts = reader.GetDateTime(1),
            name = reader.GetString(2),
            value = reader.GetDouble(3),
            tags = reader.IsDBNull(4) ? null : JsonDocument.Parse(reader.GetString(4)).RootElement,
        });
    }
    return Results.Ok(results);
});

app.Run();

record LogEntry(string Level, string Service, string Message, string? TraceId);
record TraceSpan(string TraceId, string Service, string SpanName, double DurationMs, bool IsError, Dictionary<string, object>? Attributes);
record MetricPoint(string Name, double Value, Dictionary<string, object>? Tags);

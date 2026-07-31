using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.OpenApi;
using Npgsql;
using NpgsqlTypes;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 10 * 1024 * 1024); // 10 MB cap, defense in depth alongside the per-batch item cap below
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.AllowAnyOrigin().WithMethods("GET", "POST").AllowAnyHeader()));
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c => c.SwaggerDoc("v1", new OpenApiInfo { Title = "Telemetry API", Version = "v1" }));

var app = builder.Build();
app.UseCors();
app.UseSwagger();
app.UseSwaggerUI(c =>
{
    c.SwaggerEndpoint("/swagger/v1/swagger.json", "Telemetry API v1");
    c.RoutePrefix = string.Empty;
});

var connString = Environment.GetEnvironmentVariable("DATABASE_URL")
    ?? "Host=aiops-db;Port=5432;Username=aiops;Password=aiops;Database=aiops";

// Matches the "Default Org" seeded by aiops' Alembic migration 0001. Resolved
// here (not via SQL's DEFAULT keyword, which isn't usable inside COALESCE/an
// expression — only directly in a VALUES list) so every insert always binds a
// real, non-null org_id.
var DefaultOrgId = Guid.Parse("00000000-0000-0000-0000-000000000001");

// Shared secret for first-party, same-network callers (aiops-api's webhook ->
// telemetry-api log bridge; direct curl/debugging from an operator) that have
// no per-team ingestion key of their own. Unlike an ingestion key, this grants
// access across every org, so it must never be handed to an external source.
var internalToken = Environment.GetEnvironmentVariable("TELEMETRY_INTERNAL_TOKEN");

bool IsValidInternalToken(HttpContext ctx)
{
    if (string.IsNullOrEmpty(internalToken)) return false;
    var provided = ctx.Request.Headers["X-Internal-Token"].FirstOrDefault();
    if (string.IsNullOrEmpty(provided)) return false;
    var a = Encoding.UTF8.GetBytes(provided);
    var b = Encoding.UTF8.GetBytes(internalToken);
    return a.Length == b.Length && CryptographicOperations.FixedTimeEquals(a, b);
}

async Task<NpgsqlConnection> OpenConnAsync()
{
    var conn = new NpgsqlConnection(connString);
    await conn.OpenAsync();
    return conn;
}

// ---- ingestion-key tenant tagging ----
// A team issues one of these via aiops (POST /api/teams/{id}/ingestion-keys)
// and configures their own monitoring stack to send it as X-Ingestion-Key.
// The client NEVER supplies org_id directly here — same principle as never
// trusting a client-supplied user id — it's always resolved server-side from
// the key. If the header is present but invalid/revoked we fail closed
// (401) rather than silently falling back to a default tenant.
app.Use(async (context, next) =>
{
    var ingestionKey = context.Request.Headers["X-Ingestion-Key"].FirstOrDefault();
    if (!string.IsNullOrEmpty(ingestionKey))
    {
        var keyHash = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(ingestionKey))
        ).ToLowerInvariant();

        await using var conn = await OpenConnAsync();
        Guid? keyId = null;
        await using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = """
                SELECT tik.id, tik.team_id, t.org_id
                FROM team_ingestion_keys tik JOIN teams t ON t.id = tik.team_id
                WHERE tik.key_hash = @key_hash AND tik.revoked_at IS NULL
                """;
            cmd.Parameters.AddWithValue("key_hash", keyHash);
            await using var reader = await cmd.ExecuteReaderAsync();
            if (!await reader.ReadAsync())
            {
                context.Response.StatusCode = 401;
                await context.Response.WriteAsJsonAsync(new { error = "Invalid or revoked ingestion key" });
                return;
            }
            keyId = reader.GetGuid(0);
            context.Items["TeamId"] = reader.GetInt32(1);
            context.Items["OrgId"] = reader.GetGuid(2);
        }

        // best-effort last-used bump — never block ingestion on this write
        try
        {
            await using var updateCmd = conn.CreateCommand();
            updateCmd.CommandText = "UPDATE team_ingestion_keys SET last_used_at = NOW() WHERE id = @id";
            updateCmd.Parameters.AddWithValue("id", keyId!.Value);
            await updateCmd.ExecuteNonQueryAsync();
        }
        catch (Exception ex)
        {
            app.Logger.LogWarning("Failed to bump ingestion key last_used_at: {Message}", ex.Message);
        }
    }
    await next(context);
});

// ---- authorization gate ----
// Every /api/* route (except /api/health) requires either a resolved
// ingestion key (tagged above) or the internal-service token — no request
// reaches a handler able to read/write data without one or the other.
// Closes the gap where an anonymous caller could omit both and get every
// org's data back (GET) or spoof an arbitrary org_id in the body (POST).
app.Use(async (context, next) =>
{
    var path = context.Request.Path.Value ?? "";
    if (path == "/api/health" || !path.StartsWith("/api/"))
    {
        await next(context);
        return;
    }

    var trusted = IsValidInternalToken(context);
    if (trusted) context.Items["Trusted"] = true;

    if (!context.Items.ContainsKey("OrgId") && !trusted)
    {
        context.Response.StatusCode = 401;
        await context.Response.WriteAsJsonAsync(new { error = "Missing or invalid X-Ingestion-Key / X-Internal-Token" });
        return;
    }
    await next(context);
});

// Resolves the org_id to WRITE. An ingestion key always wins over whatever
// the body claims (a team's key can never write data under a different
// org's name); the internal token, being fully trusted, honors the body.
Guid ResolveOrgId(HttpContext ctx, Guid? bodyOrgId)
{
    if (ctx.Items.TryGetValue("OrgId", out var v) && v is Guid orgId) return orgId;
    return bodyOrgId ?? DefaultOrgId;
}

// Resolves the org_id to READ by. An ingestion key hard-scopes the caller to
// their own org, ignoring/overriding whatever org_id query param was passed;
// the internal token may pass any org_id (or none, for "every org").
Guid? EffectiveOrgFilter(HttpContext ctx, Guid? requestedOrgId)
{
    if (ctx.Items.TryGetValue("OrgId", out var v) && v is Guid orgId) return orgId;
    return requestedOrgId;
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
                CREATE TABLE IF NOT EXISTS metrics (
                    id                  BIGSERIAL PRIMARY KEY,
                    ts                  TIMESTAMPTZ NOT NULL,
                    service             TEXT NOT NULL,
                    error_rate          NUMERIC(5,3),
                    p99_latency_ms      NUMERIC(8,1),
                    active_connections  INTEGER,
                    rss_mb              NUMERIC(8,1)
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_service_ts ON metrics (service, ts);

                CREATE TABLE IF NOT EXISTS logs (
                    id       BIGSERIAL PRIMARY KEY,
                    ts       TIMESTAMPTZ NOT NULL,
                    service  TEXT NOT NULL,
                    level    TEXT NOT NULL,
                    event    TEXT NOT NULL,
                    trace_id TEXT,
                    message  TEXT,
                    context  JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_logs_service_ts ON logs (service, ts);
                CREATE INDEX IF NOT EXISTS idx_logs_trace_id ON logs (trace_id);

                CREATE TABLE IF NOT EXISTS traces (
                    id          BIGSERIAL PRIMARY KEY,
                    ts          TIMESTAMPTZ NOT NULL,
                    trace_id    TEXT NOT NULL,
                    service     TEXT NOT NULL,
                    span_name   TEXT NOT NULL,
                    duration_ms NUMERIC(10,2) NOT NULL,
                    is_error    BOOLEAN NOT NULL DEFAULT FALSE,
                    error_code  TEXT,
                    attributes  JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces (trace_id);
                CREATE INDEX IF NOT EXISTS idx_traces_service_ts ON traces (service, ts);

                CREATE TABLE IF NOT EXISTS cases (
                    id              BIGSERIAL PRIMARY KEY,
                    status          TEXT NOT NULL,
                    primary_service TEXT,
                    opened_at       TIMESTAMPTZ,
                    updated_at      TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id              BIGSERIAL PRIMARY KEY,
                    case_id         BIGINT REFERENCES cases(id),
                    source_tool     TEXT NOT NULL,
                    raw_alert_id    TEXT,
                    service         TEXT NOT NULL,
                    metric          TEXT NOT NULL,
                    severity        TEXT,
                    triggered_at    TIMESTAMPTZ,
                    received_at     TIMESTAMPTZ,
                    duplicate_count INTEGER DEFAULT 1,
                    raw_payload     JSONB
                );
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

NpgsqlParameter Param(string name, NpgsqlDbType type, object? value) => new(name, type) { Value = value ?? DBNull.Value };

NpgsqlParameter JsonbParam(string name, object? value) => new(name, NpgsqlDbType.Jsonb)
{
    Value = value is null ? DBNull.Value : JsonSerializer.Serialize(value)
};

await InitDbAsync();

const int MaxBatchSize = 5000;

app.MapGet("/api/health", () => Results.Ok(new { status = "ok" }));

// ---- logs ----

app.MapPost("/api/logs", async (LogEntry[] entries, HttpContext httpContext) =>
{
    if (entries.Length > MaxBatchSize)
        return Results.BadRequest(new { error = $"Batch too large — max {MaxBatchSize} entries per request" });

    await using var conn = await OpenConnAsync();
    await using var tx = await conn.BeginTransactionAsync();
    foreach (var e in entries)
    {
        await using var cmd = conn.CreateCommand();
        cmd.Transaction = (NpgsqlTransaction)tx;
        // org_id is omittable — if the caller doesn't resolve one yet (no
        // per-team ingestion key configured, see Phase 4), it falls back to
        // DefaultOrgId above.
        cmd.CommandText = "INSERT INTO logs (ts, service, level, event, trace_id, message, context, org_id) VALUES (NOW(), @service, @level, @event, @trace_id, @message, @context, @org_id)";
        cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, e.Service));
        cmd.Parameters.Add(Param("level", NpgsqlDbType.Text, e.Level));
        cmd.Parameters.Add(Param("event", NpgsqlDbType.Text, e.Event));
        cmd.Parameters.Add(Param("trace_id", NpgsqlDbType.Text, e.TraceId));
        cmd.Parameters.Add(Param("message", NpgsqlDbType.Text, e.Message));
        cmd.Parameters.Add(JsonbParam("context", e.Context));
        cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, ResolveOrgId(httpContext, e.OrgId)));
        await cmd.ExecuteNonQueryAsync();
    }
    await tx.CommitAsync();
    return Results.Accepted(value: new { inserted = entries.Length });
});

app.MapGet("/api/logs", async (HttpContext httpContext, string? service, Guid? org_id, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, service, level, event, trace_id, message, context, org_id FROM logs WHERE (@service IS NULL OR service = @service) AND (@org_id IS NULL OR org_id = @org_id) ORDER BY ts DESC LIMIT @limit";
    cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, service));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            ts = reader.GetDateTime(1),
            service = reader.GetString(2),
            level = reader.GetString(3),
            @event = reader.GetString(4),
            trace_id = reader.IsDBNull(5) ? null : reader.GetString(5),
            message = reader.IsDBNull(6) ? null : reader.GetString(6),
            context = reader.IsDBNull(7) ? (JsonElement?)null : JsonDocument.Parse(reader.GetString(7)).RootElement,
            org_id = reader.GetGuid(8),
        });
    }
    return Results.Ok(results);
});

// ---- traces ----

app.MapPost("/api/traces", async (TraceSpan[] spans, HttpContext httpContext) =>
{
    if (spans.Length > MaxBatchSize)
        return Results.BadRequest(new { error = $"Batch too large — max {MaxBatchSize} entries per request" });

    await using var conn = await OpenConnAsync();
    await using var tx = await conn.BeginTransactionAsync();
    foreach (var s in spans)
    {
        await using var cmd = conn.CreateCommand();
        cmd.Transaction = (NpgsqlTransaction)tx;
        cmd.CommandText = "INSERT INTO traces (ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes, org_id) VALUES (NOW(), @trace_id, @service, @span_name, @duration_ms, @is_error, @error_code, @attributes, @org_id)";
        cmd.Parameters.Add(Param("trace_id", NpgsqlDbType.Text, s.TraceId));
        cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, s.Service));
        cmd.Parameters.Add(Param("span_name", NpgsqlDbType.Text, s.SpanName));
        cmd.Parameters.Add(Param("duration_ms", NpgsqlDbType.Numeric, s.DurationMs));
        cmd.Parameters.Add(Param("is_error", NpgsqlDbType.Boolean, s.IsError));
        cmd.Parameters.Add(Param("error_code", NpgsqlDbType.Text, s.ErrorCode));
        cmd.Parameters.Add(JsonbParam("attributes", s.Attributes));
        cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, ResolveOrgId(httpContext, s.OrgId)));
        await cmd.ExecuteNonQueryAsync();
    }
    await tx.CommitAsync();
    return Results.Accepted(value: new { inserted = spans.Length });
});

app.MapGet("/api/traces/{traceId}", async (HttpContext httpContext, string traceId, Guid? org_id) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes, org_id FROM traces WHERE trace_id = @trace_id AND (@org_id IS NULL OR org_id = @org_id) ORDER BY ts";
    cmd.Parameters.AddWithValue("trace_id", traceId);
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            ts = reader.GetDateTime(1),
            trace_id = reader.GetString(2),
            service = reader.GetString(3),
            span_name = reader.GetString(4),
            duration_ms = reader.GetDecimal(5),
            is_error = reader.GetBoolean(6),
            error_code = reader.IsDBNull(7) ? null : reader.GetString(7),
            attributes = reader.IsDBNull(8) ? (JsonElement?)null : JsonDocument.Parse(reader.GetString(8)).RootElement,
            org_id = reader.GetGuid(9),
        });
    }
    return Results.Ok(results);
});

app.MapGet("/api/traces", async (HttpContext httpContext, string? service, Guid? org_id, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes, org_id FROM traces WHERE (@service IS NULL OR service = @service) AND (@org_id IS NULL OR org_id = @org_id) ORDER BY ts DESC LIMIT @limit";
    cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, service));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            ts = reader.GetDateTime(1),
            trace_id = reader.GetString(2),
            service = reader.GetString(3),
            span_name = reader.GetString(4),
            duration_ms = reader.GetDecimal(5),
            is_error = reader.GetBoolean(6),
            error_code = reader.IsDBNull(7) ? null : reader.GetString(7),
            attributes = reader.IsDBNull(8) ? (JsonElement?)null : JsonDocument.Parse(reader.GetString(8)).RootElement,
            org_id = reader.GetGuid(9),
        });
    }
    return Results.Ok(results);
});

// ---- metrics ----

app.MapPost("/api/metrics", async (MetricPoint[] points, HttpContext httpContext) =>
{
    if (points.Length > MaxBatchSize)
        return Results.BadRequest(new { error = $"Batch too large — max {MaxBatchSize} entries per request" });

    await using var conn = await OpenConnAsync();
    await using var tx = await conn.BeginTransactionAsync();
    foreach (var m in points)
    {
        await using var cmd = conn.CreateCommand();
        cmd.Transaction = (NpgsqlTransaction)tx;
        cmd.CommandText = "INSERT INTO metrics (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb, org_id) VALUES (NOW(), @service, @error_rate, @p99_latency_ms, @active_connections, @rss_mb, @org_id)";
        cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, m.Service));
        cmd.Parameters.Add(Param("error_rate", NpgsqlDbType.Numeric, m.ErrorRate));
        cmd.Parameters.Add(Param("p99_latency_ms", NpgsqlDbType.Numeric, m.P99LatencyMs));
        cmd.Parameters.Add(Param("active_connections", NpgsqlDbType.Integer, m.ActiveConnections));
        cmd.Parameters.Add(Param("rss_mb", NpgsqlDbType.Numeric, m.RssMb));
        cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, ResolveOrgId(httpContext, m.OrgId)));
        await cmd.ExecuteNonQueryAsync();
    }
    await tx.CommitAsync();
    return Results.Accepted(value: new { inserted = points.Length });
});

app.MapGet("/api/metrics", async (HttpContext httpContext, string? service, Guid? org_id, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, ts, service, error_rate, p99_latency_ms, active_connections, rss_mb, org_id FROM metrics WHERE (@service IS NULL OR service = @service) AND (@org_id IS NULL OR org_id = @org_id) ORDER BY ts DESC LIMIT @limit";
    cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, service));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            ts = reader.GetDateTime(1),
            service = reader.GetString(2),
            error_rate = reader.IsDBNull(3) ? (decimal?)null : reader.GetDecimal(3),
            p99_latency_ms = reader.IsDBNull(4) ? (decimal?)null : reader.GetDecimal(4),
            active_connections = reader.IsDBNull(5) ? (int?)null : reader.GetInt32(5),
            rss_mb = reader.IsDBNull(6) ? (decimal?)null : reader.GetDecimal(6),
            org_id = reader.GetGuid(7),
        });
    }
    return Results.Ok(results);
});

// ---- cases ----

app.MapPost("/api/cases", async (CaseRecord c, HttpContext httpContext) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = """
        INSERT INTO cases (status, primary_service, opened_at, updated_at, org_id)
        VALUES (@status, @primary_service, NOW(), NOW(), @org_id)
        RETURNING id
        """;
    cmd.Parameters.Add(Param("status", NpgsqlDbType.Text, c.Status));
    cmd.Parameters.Add(Param("primary_service", NpgsqlDbType.Text, c.PrimaryService));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, ResolveOrgId(httpContext, c.OrgId)));
    var id = (long)(await cmd.ExecuteScalarAsync())!;
    return Results.Created($"/api/cases/{id}", new { id });
});

app.MapGet("/api/cases", async (HttpContext httpContext, string? status, Guid? org_id, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, status, primary_service, opened_at, updated_at, org_id FROM cases WHERE (@status IS NULL OR status = @status) AND (@org_id IS NULL OR org_id = @org_id) ORDER BY opened_at DESC LIMIT @limit";
    cmd.Parameters.Add(Param("status", NpgsqlDbType.Text, status));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            status = reader.GetString(1),
            primary_service = reader.IsDBNull(2) ? null : reader.GetString(2),
            opened_at = reader.IsDBNull(3) ? (DateTime?)null : reader.GetDateTime(3),
            updated_at = reader.IsDBNull(4) ? (DateTime?)null : reader.GetDateTime(4),
            org_id = reader.GetGuid(5),
        });
    }
    return Results.Ok(results);
});

app.MapGet("/api/cases/{id:long}", async (HttpContext httpContext, long id, Guid? org_id) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, status, primary_service, opened_at, updated_at, org_id FROM cases WHERE id = @id AND (@org_id IS NULL OR org_id = @org_id)";
    cmd.Parameters.AddWithValue("id", id);
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    await using var reader = await cmd.ExecuteReaderAsync();
    if (!await reader.ReadAsync()) return Results.NotFound();
    return Results.Ok(new
    {
        id = reader.GetInt64(0),
        status = reader.GetString(1),
        primary_service = reader.IsDBNull(2) ? null : reader.GetString(2),
        opened_at = reader.IsDBNull(3) ? (DateTime?)null : reader.GetDateTime(3),
        updated_at = reader.IsDBNull(4) ? (DateTime?)null : reader.GetDateTime(4),
        org_id = reader.GetGuid(5),
    });
});

// ---- alerts ----

app.MapPost("/api/alerts", async (AlertRecord a, HttpContext httpContext) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = """
        INSERT INTO alerts (case_id, source_tool, raw_alert_id, service, metric, severity, triggered_at, received_at, duplicate_count, raw_payload, org_id)
        VALUES (@case_id, @source_tool, @raw_alert_id, @service, @metric, @severity, NOW(), NOW(), @duplicate_count, @raw_payload, @org_id)
        RETURNING id
        """;
    cmd.Parameters.Add(Param("case_id", NpgsqlDbType.Bigint, a.CaseId));
    cmd.Parameters.Add(Param("source_tool", NpgsqlDbType.Text, a.SourceTool));
    cmd.Parameters.Add(Param("raw_alert_id", NpgsqlDbType.Text, a.RawAlertId));
    cmd.Parameters.Add(Param("service", NpgsqlDbType.Text, a.Service));
    cmd.Parameters.Add(Param("metric", NpgsqlDbType.Text, a.Metric));
    cmd.Parameters.Add(Param("severity", NpgsqlDbType.Text, a.Severity));
    cmd.Parameters.Add(Param("duplicate_count", NpgsqlDbType.Integer, a.DuplicateCount ?? 1));
    cmd.Parameters.Add(JsonbParam("raw_payload", a.RawPayload));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, ResolveOrgId(httpContext, a.OrgId)));
    var id = (long)(await cmd.ExecuteScalarAsync())!;
    return Results.Created($"/api/alerts/{id}", new { id });
});

app.MapGet("/api/alerts", async (HttpContext httpContext, long? case_id, Guid? org_id, int limit = 100) =>
{
    await using var conn = await OpenConnAsync();
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = "SELECT id, case_id, source_tool, raw_alert_id, service, metric, severity, triggered_at, received_at, duplicate_count, raw_payload, org_id FROM alerts WHERE (@case_id IS NULL OR case_id = @case_id) AND (@org_id IS NULL OR org_id = @org_id) ORDER BY triggered_at DESC LIMIT @limit";
    cmd.Parameters.Add(Param("case_id", NpgsqlDbType.Bigint, case_id));
    cmd.Parameters.Add(Param("org_id", NpgsqlDbType.Uuid, EffectiveOrgFilter(httpContext, org_id)));
    cmd.Parameters.AddWithValue("limit", limit <= 0 ? 100 : limit);
    await using var reader = await cmd.ExecuteReaderAsync();
    var results = new List<object>();
    while (await reader.ReadAsync())
    {
        results.Add(new
        {
            id = reader.GetInt64(0),
            case_id = reader.IsDBNull(1) ? (long?)null : reader.GetInt64(1),
            source_tool = reader.GetString(2),
            raw_alert_id = reader.IsDBNull(3) ? null : reader.GetString(3),
            service = reader.GetString(4),
            metric = reader.GetString(5),
            severity = reader.IsDBNull(6) ? null : reader.GetString(6),
            triggered_at = reader.IsDBNull(7) ? (DateTime?)null : reader.GetDateTime(7),
            received_at = reader.IsDBNull(8) ? (DateTime?)null : reader.GetDateTime(8),
            duplicate_count = reader.IsDBNull(9) ? (int?)null : reader.GetInt32(9),
            raw_payload = reader.IsDBNull(10) ? (JsonElement?)null : JsonDocument.Parse(reader.GetString(10)).RootElement,
            org_id = reader.GetGuid(11),
        });
    }
    return Results.Ok(results);
});

app.Run();

// OrgId is optional on every ingest payload — until Phase 4's per-team
// ingestion keys exist to resolve it server-side, omitting it just falls
// through to each table's org_id column DEFAULT (Default Org).
record LogEntry(string Service, string Level, string Event, string? TraceId, string? Message, Dictionary<string, object>? Context, Guid? OrgId = null);
record TraceSpan(string TraceId, string Service, string SpanName, decimal DurationMs, bool IsError, string? ErrorCode, Dictionary<string, object>? Attributes, Guid? OrgId = null);
record MetricPoint(string Service, decimal? ErrorRate, decimal? P99LatencyMs, int? ActiveConnections, decimal? RssMb, Guid? OrgId = null);
record CaseRecord(string Status, string? PrimaryService, Guid? OrgId = null);
record AlertRecord(long? CaseId, string SourceTool, string? RawAlertId, string Service, string Metric, string? Severity, int? DuplicateCount, Dictionary<string, object>? RawPayload, Guid? OrgId = null);

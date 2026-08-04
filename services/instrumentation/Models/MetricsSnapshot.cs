public sealed class MetricsSnapshot
{
    public int TotalRequests { get; init; }

    public int ErrorCount { get; init; }

    public double ErrorRate { get; init; }

    public double P99LatencyMs { get; init; }
}
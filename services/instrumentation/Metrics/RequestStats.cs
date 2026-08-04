using System.Collections.Concurrent;

namespace Instrumentation.Metrics;

public sealed class RequestStats
{
    private int _totalRequests;
    private int _failedRequests;

    private readonly ConcurrentQueue<double> _latencies = new();

    public void Record(bool success, double latencyMs)
    {
        Interlocked.Increment(ref _totalRequests);

        if (!success)
        {
            Interlocked.Increment(ref _failedRequests);
        }

        _latencies.Enqueue(latencyMs);
    }

    public MetricsSnapshot TakeSnapshotAndReset()
    {
        var total = Interlocked.Exchange(ref _totalRequests, 0);
        var failed = Interlocked.Exchange(ref _failedRequests, 0);

        var latencies = new List<double>();

        while (_latencies.TryDequeue(out var latency))
        {
            latencies.Add(latency);
        }

        latencies.Sort();

        double p99 = 0;

        if (latencies.Count > 0)
        {
            var index = (int)Math.Ceiling(latencies.Count * 0.99) - 1;
            index = Math.Clamp(index, 0, latencies.Count - 1);

            p99 = latencies[index];
        }

        return new MetricsSnapshot
        {
            TotalRequests = total,
            ErrorCount = failed,
            ErrorRate = total == 0
                ? 0
                : (double)failed / total,

            P99LatencyMs = p99
        };
    }
}
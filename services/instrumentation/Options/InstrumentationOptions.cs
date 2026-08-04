namespace Instrumentation.Options;

public sealed class InstrumentationOptions
{
    public required string ServiceName { get; set; }
    public required string ConnectionString { get; set; }
    public TimeSpan MetricsFlushInterval { get; set; } = TimeSpan.FromSeconds(5);
    public Func<string>? ServiceVersionProvider { get; set; }
}
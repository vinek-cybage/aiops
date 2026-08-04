namespace Instrumentation.Models;

/// <summary>
/// Data associated with a single HTTP request.
/// </summary>
public sealed class RequestContext
{
    public required string TraceId { get; init; }
}
namespace Instrumentation.Models;

public sealed class RequestFaultContext
{
    public string? Event { get; private set; }

    public string? Message { get; private set; }

    public string? Level { get; private set; }

    public Dictionary<string, object?> Properties { get; } = [];

    public void Set(
        string @event,
        string message,
        string level,
        Dictionary<string, object?> properties)
    {
        Event = @event;
        Message = message;
        Level = level;

        foreach (var property in properties)
        {
            Properties[property.Key] = property.Value;
        }
    }
}
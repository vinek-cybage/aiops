public sealed class DbConnectionTracker
{
    private int _activeConnections;
    public const int MaxPoolSize = 50;

    public int ActiveConnections => Volatile.Read(ref _activeConnections);

    public void Open()
    {
        Interlocked.Increment(ref _activeConnections);
    }

    public void Close()
    {
        Interlocked.Decrement(ref _activeConnections);
    }

    public void Reset()
    {
        Interlocked.Exchange(ref _activeConnections, 0);
    }
}
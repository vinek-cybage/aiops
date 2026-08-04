using System.Diagnostics;
namespace OrdersService.Faults;

public sealed class ConcurrencyLimitSimulator
{
    private int _concurrentRequests;
    public bool Enabled = false;
    public static int MaxConcurrentRequests = 4;

    public bool TryEnter()
    {
        var concurrentRequests = Interlocked.Increment(ref _concurrentRequests);

        if (concurrentRequests <= MaxConcurrentRequests)
        {
            return true;
        }

        Interlocked.Decrement(ref _concurrentRequests);
        return false;
    }

    public void Exit()
    {
        Interlocked.Decrement(ref _concurrentRequests);
    }
}
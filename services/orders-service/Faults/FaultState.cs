using System.Collections.Concurrent;

namespace OrdersService.Faults;

public static class FaultState
{

    public static bool BadDeployEnabled = false;
    public const string HealthyVersion = "v126";
    public const string FaultyVersion = "v127";
    public static string CurrentVersion = HealthyVersion;
    public static bool MemoryLeakEnabled = false;
    public static ConcurrentBag<byte[]> LeakedMemory { get; } = new();
    public static bool DbConnectionLeakEnabled = false;
}
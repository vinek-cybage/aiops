using OrdersService.Faults;
using OrdersService.Models;
using Instrumentation.Constants;
using Instrumentation.Models;

namespace OrdersService.Services;

public sealed class OrderProcessor
{
    private readonly CpuThrottleSimulator _cpuThrottleSimulator;
    private readonly RequestFaultContext _requestFaultContext;
    private readonly ConcurrencyLimitSimulator _concurrencyLimitSimulator;
    private readonly DbConnectionTracker _dbConnectionTracker;

    public OrderProcessor(
        CpuThrottleSimulator cpuThrottleSimulator,
        ConcurrencyLimitSimulator concurrencyLimitSimulator,
        RequestFaultContext requestFaultContext,
        DbConnectionTracker dbConnectionTracker)
    {
        _cpuThrottleSimulator = cpuThrottleSimulator;
        _requestFaultContext = requestFaultContext;
        _concurrencyLimitSimulator = concurrencyLimitSimulator;
        _dbConnectionTracker = dbConnectionTracker;
    }

    public OrderProcessingResult GetOrder(int orderId)
    {
        
        if (FaultState.BadDeployEnabled)
        {
            _requestFaultContext.Set(
                LogEvents.UnhandledException,
                $"TypeError: unsupported operand in pricing calc.",
                LogLevels.Error,
                new Dictionary<string, object?>
                {
                    ["handler"] = "get_order",
                    ["version"] = FaultState.CurrentVersion
                });

            throw new InvalidOperationException(
                $"Order processing failed in version {FaultState.CurrentVersion}.");
        }


        if (_cpuThrottleSimulator.Enabled)
        {
            _cpuThrottleSimulator.DoBusyWork();
        }

        if (FaultState.MemoryLeakEnabled)
        {
            const int AllocationSize = 20 * 1024 * 1024; // 20 MB per request

            var buffer = new byte[AllocationSize];

            // Touch one byte per memory page so the OS commits
            // the pages into the process working set (RSS).
            for (int i = 0; i < buffer.Length; i += 4096)
            {
                buffer[i] = 1;
            }

            FaultState.LeakedMemory.Add(buffer);
        }

        if (_concurrencyLimitSimulator.Enabled)
        {
            if (!_concurrencyLimitSimulator.TryEnter())
            {
                _requestFaultContext.Set(
                    LogEvents.RateLimited,
                    "Concurrency limit exceeded for get_order.",
                    LogLevels.Warning,
                    new Dictionary<string, object?>
                    {
                        ["handler"] = "get_order",
                        ["version"] = FaultState.CurrentVersion
                    });

                return OrderProcessingResult.RateLimited();
            }
        }

        if (FaultState.DbConnectionLeakEnabled)
        {
            if (_dbConnectionTracker.ActiveConnections >= DbConnectionTracker.MaxPoolSize)
            {
                _requestFaultContext.Set(
                    LogEvents.DatabaseConnectionsExhausted,
                    "Database connections exhausted for get_order.",
                    LogLevels.Error,
                    new Dictionary<string, object?>
                    {
                        ["handler"] = "get_order",
                        ["version"] = FaultState.CurrentVersion
                    });
                return OrderProcessingResult.DatabaseUnavailable();
            }

            _dbConnectionTracker.Open();

            // Intentionally never Close()
        }


        return OrderProcessingResult.Success(
            new OrderResponse
            {
                OrderId = orderId,
                CustomerName = "John Doe",
                Amount = 249.99m,
                Status = "Confirmed"
            });
    }
}

public sealed class OrderProcessingResult
{
    public OrderResponse? Order { get; init; }

    public bool IsRateLimited { get; init; }
    public bool IsDatabaseUnavailable { get; private set; }

    public static OrderProcessingResult Success(OrderResponse order) =>
        new() { Order = order };

    public static OrderProcessingResult RateLimited() =>
        new() { IsRateLimited = true };

    internal static OrderProcessingResult DatabaseUnavailable() => 
        new() { IsDatabaseUnavailable = true };
}
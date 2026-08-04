using Microsoft.AspNetCore.Mvc;
using OrdersService.Faults;
using Instrumentation.Constants;
using Instrumentation.Logging;
namespace OrdersService.Controllers;

[ApiController]
[Route("admin")]
public class AdminController : ControllerBase
{
    private readonly LogWriter _logWriter;
    private readonly CpuThrottleSimulator _cpuThrottleSimulator;
    private readonly ConcurrencyLimitSimulator _concurrencyLimitSimulator;
    private readonly DbConnectionTracker _dbConnectionTracker;

    public AdminController(
    LogWriter logWriter,
    CpuThrottleSimulator cpuThrottleSimulator,
    ConcurrencyLimitSimulator concurrencyLimitSimulator,
    DbConnectionTracker dbConnectionTracker)
    {
        _logWriter = logWriter;
        _cpuThrottleSimulator = cpuThrottleSimulator;
        _concurrencyLimitSimulator = concurrencyLimitSimulator;
        _dbConnectionTracker = dbConnectionTracker;
    }


    [HttpPost("deploy")]
    public async Task<IActionResult> Deploy()
    {
        var previousVersion = FaultState.CurrentVersion;

        FaultState.BadDeployEnabled = true;
        FaultState.CurrentVersion = FaultState.FaultyVersion;

        await _logWriter.WriteAsync(
            LogLevels.Information,
            LogEvents.Deployment,
            null,
            $"Deployed version {FaultState.CurrentVersion}",
            new
            {
                version = FaultState.CurrentVersion,
                previous_version = previousVersion
            });

        return Ok(new
        {
            message = "Deployment completed.",
            version = FaultState.CurrentVersion
        });
    }

    [HttpPost("rollback")]
    public async Task<IActionResult> RollBack()
    {
        var previousVersion = FaultState.CurrentVersion;

        FaultState.BadDeployEnabled = false;
        FaultState.CurrentVersion = FaultState.HealthyVersion;

        await _logWriter.WriteAsync(
            LogLevels.Information,
            LogEvents.Deployment,
            null,
            $"Deployed version {FaultState.CurrentVersion}",
            new
            {
                version = FaultState.CurrentVersion,
                previous_version = previousVersion
            });

        return Ok(new
        {
            message = "Rollback completed.",
            version = FaultState.CurrentVersion
        });
    }

    [HttpPost("cpu-throttle/on")]
    public async Task<IActionResult> EnableCpuThrottle()
    {
        _cpuThrottleSimulator.Enabled = true;
        return Ok(new
        {
            enabled = true
        });
    }

    [HttpPost("concurrency-limit/on")]
    public async Task<IActionResult> EnableConcurrencyLimit()
    {
        _concurrencyLimitSimulator.Enabled = true;
        return Ok(new
        {
            enabled = true
        });
    }

    [HttpPost("scale-out")]
    public async Task<IActionResult> ScaleOut()
    {
        _cpuThrottleSimulator.Enabled = false;
        _concurrencyLimitSimulator.Enabled = false;
        return Ok(new
        {
            enabled = false
        });
    }

    [HttpPost("memory-leak/on")]
    public async Task<IActionResult> EnableMemoryLeak()
    {
        FaultState.MemoryLeakEnabled = true;
        return Ok(new
        {
            enabled = true
        });
    }

    [HttpPost("database-connection-leak/on")]
    public async Task<IActionResult> EnableDbConnectionLeak()
    {
        FaultState.DbConnectionLeakEnabled = true;
        return Ok(new
        {
            enabled = true
        });
    }

    [HttpPost("restart-pod")]
    public async Task<IActionResult> RestartPod()
    {
        FaultState.MemoryLeakEnabled = false;
        FaultState.LeakedMemory.Clear();
        FaultState.DbConnectionLeakEnabled = false;
        _dbConnectionTracker.Reset();
        return Ok(new
        {
            enabled = false
        });
    }
}
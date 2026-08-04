using System.Diagnostics;

namespace OrdersService.Faults;

public sealed class CpuThrottleSimulator
{
    public bool Enabled = false;

    public int BusyWorkMs { get; set; } = 500; // Default to 500 ms of busy work

    public void DoBusyWork()
    {
        var until = Stopwatch.GetTimestamp() +
            (long)(Stopwatch.Frequency * BusyWorkMs / 1000d);

        while (Stopwatch.GetTimestamp() < until)
        {
            Thread.SpinWait(1_000);
        }
    }
}
using Microsoft.AspNetCore.Mvc;
using PaymentsService.Faults;
using Instrumentation.Constants;
using Instrumentation.Models;

[ApiController]
[Route("payments")]
public class PaymentsController : ControllerBase
{
    private readonly RequestFaultContext _requestFaultContext;

    public PaymentsController(RequestFaultContext requestFaultContext)
    {
        _requestFaultContext = requestFaultContext;
    }

    [HttpPost("charge")]
    public async Task<IActionResult> Charge([FromBody] ChargeRequest req)
    {
        var provider = FaultState.CurrentPaymentProvider; // "paypal" by default

        if (FaultState.BadPaymentProvider && provider == "Stripe")
        {
            _requestFaultContext.Set(
                   LogEvents.PaymentFailed,
                   $"payment request failed due to {provider} API unavailable",
                   LogLevels.Error,
                   new Dictionary<string, object?>
                   {
                       ["provider"] = FaultState.CurrentPaymentProvider
                   });

            return StatusCode(StatusCodes.Status503ServiceUnavailable, new { error = "Payment provider unavailable" });
        }

        // simulate the "third-party" call itself — just a small delay, no real network call
        await Task.Delay(Random.Shared.Next(50, 150));

        return Ok(new { status = "success", provider });
    }


    public class ChargeRequest
    {
        public int OrderId { get; set; }
        public decimal Amount { get; set; }
    }
}

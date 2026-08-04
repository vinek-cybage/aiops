using Microsoft.AspNetCore.Mvc;
using PaymentsService.Faults;
using Instrumentation.Logging;

namespace OrdersService.Controllers;

[ApiController]
[Route("admin")]
public class AdminController : ControllerBase
{

    [HttpPost("payment-provider/stripe")]
    public async Task<IActionResult> EnableBadPaymentProvider()
    {
        FaultState.BadPaymentProvider = true;
        FaultState.CurrentPaymentProvider = FaultState.StripePaymentProvider;

        return Ok(new
        {
            message = "Bad payment provider enabled.",
            provider = FaultState.CurrentPaymentProvider
        });
    }

    [HttpPost("payment-provider/paypal")]
    public async Task<IActionResult> DisableBadPaymentProvider()
    {
        FaultState.BadPaymentProvider = false;
        FaultState.CurrentPaymentProvider = FaultState.PaypalPaymentProvider;

        return Ok(new
        {
            message = "Bad payment provider disabled.",
            provider = FaultState.CurrentPaymentProvider
        });
    }

}
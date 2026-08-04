using Microsoft.AspNetCore.Mvc;
using OrdersService.Models;
using OrdersService.Services;

namespace OrdersService.Controllers;

[ApiController]
[Route("orders")]
public class OrdersController : ControllerBase
{
    private readonly OrderProcessor _orderProcessor;
    private readonly PaymentsProcessor _paymentsProcessor;

    public OrdersController(PaymentsProcessor paymentsProcessor, OrderProcessor orderProcessor)
    {
        _paymentsProcessor = paymentsProcessor;
        _orderProcessor = orderProcessor;
    }

    [HttpGet("{id:int}")]
    [ProducesResponseType<OrderResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status429TooManyRequests)]
    [ProducesResponseType(StatusCodes.Status500InternalServerError)]
    public ActionResult<OrderResponse> GetOrder(int id)
    {
        var result = _orderProcessor.GetOrder(id);

        if (result.IsRateLimited)
        {
            return StatusCode(StatusCodes.Status429TooManyRequests);
        }
        else if (result.IsDatabaseUnavailable)
        {
            return StatusCode(StatusCodes.Status500InternalServerError, new { error = "Database unavailable" });
        }

        return Ok(result.Order);
    }

    [HttpPost("{id}/checkout")]
    public async Task<IActionResult> Checkout(int id)
    {

        try
        {
            var response = await _paymentsProcessor.ProcessPaymentAsync(id, 100.00m); // Example amount
            return Ok(new { orderId = id, status = "confirmed" });
        }
        catch (Exception)
        {
            return StatusCode(StatusCodes.Status502BadGateway, new { error = "Checkout failed: payment processing unavailable" });
        }
    }
}
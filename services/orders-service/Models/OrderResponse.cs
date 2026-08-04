namespace OrdersService.Models;

public sealed class OrderResponse
{
    public int OrderId { get; init; }

    public string CustomerName { get; init; } = string.Empty;

    public decimal Amount { get; init; }

    public string Status { get; init; } = string.Empty;
}
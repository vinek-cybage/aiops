namespace OrdersService.Models;

public sealed class PaymentResponse
{
    public string Provider { get; init; } = string.Empty;

    public string Error { get; init; } = string.Empty;

    public string Status { get; init; } = string.Empty;
}
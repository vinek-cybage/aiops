using OrdersService.Models;

public sealed class PaymentsProcessor
{
    private readonly IHttpClientFactory _httpClientFactory;

    private readonly PaymentServiceOptions _paymentServiceOptions;

    public PaymentsProcessor(
        IHttpClientFactory httpClientFactory,
        PaymentServiceOptions options)
    {
        _httpClientFactory = httpClientFactory;
        _paymentServiceOptions = options;
    }

    public async Task<PaymentResponse> ProcessPaymentAsync(int orderId, decimal amount)
    {
        var client = _httpClientFactory.CreateClient("payments-service");
        var paymentRequest = new { OrderId = orderId, Amount = amount };
        var response = await client.PostAsJsonAsync("/payments/charge", paymentRequest);

        if (response.IsSuccessStatusCode)
        {
            var paymentResponse = await response.Content.ReadFromJsonAsync<PaymentResponse>();
            return paymentResponse ?? throw new InvalidOperationException("Failed to deserialize payment response");
        }
        else
        {
            throw new InvalidOperationException($"Payment service returned status code {response.StatusCode}");
        }
    }
}
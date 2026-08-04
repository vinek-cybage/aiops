namespace PaymentsService.Faults;

public static class FaultState
{
    public const string StripePaymentProvider = "Stripe";
    public const string PaypalPaymentProvider = "Paypal";
    public static string CurrentPaymentProvider = PaypalPaymentProvider;
    public static bool BadPaymentProvider = false;
    public const string CurrentVersion = "1.0.0";
}
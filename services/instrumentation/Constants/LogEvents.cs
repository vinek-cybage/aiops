namespace Instrumentation.Constants;

public static class LogEvents
{
    public const string RequestHandled = "request_handled";

    public const string UnhandledException = "unhandled_exception";

    public const string Deployment = "deployment";

    public const string HttpRequestFailed = "http_request_failed";

    public const string RateLimited = "rate_limited";

    public const string PaymentFailed = "payment_failed";

    public const string DatabaseConnectionsExhausted = "database_connections_exhausted";
}
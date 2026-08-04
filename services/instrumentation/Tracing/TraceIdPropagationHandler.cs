using Microsoft.AspNetCore.Http;
using Instrumentation.Constants;
using Instrumentation.Models;

namespace Instrumentation.Tracing;

public sealed class TraceIdPropagationHandler(
    IHttpContextAccessor httpContextAccessor)
    : DelegatingHandler
{
    private readonly IHttpContextAccessor _httpContextAccessor = httpContextAccessor;

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        var httpContext = _httpContextAccessor.HttpContext;

        if (httpContext?.Items.TryGetValue(
                InstrumentationConstants.RequestContextKey,
                out var value) == true &&
            value is RequestContext requestContext &&
            !request.Headers.Contains(InstrumentationConstants.TraceIdHeader))
        {
            request.Headers.Add(
                InstrumentationConstants.TraceIdHeader,
                requestContext.TraceId);
        }

        return base.SendAsync(request, cancellationToken);
    }
}
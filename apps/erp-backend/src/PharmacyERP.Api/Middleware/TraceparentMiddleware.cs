using Microsoft.AspNetCore.Http;

namespace PharmacyERP.Api.Middleware;

public class TraceparentMiddleware
{
    private readonly RequestDelegate _next;
    public const string TraceparentHeaderName = "traceparent";
    public const string CustomTraceIdHeaderName = "X-Trace-Id";

    public TraceparentMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var incomingTraceparent = context.Request.Headers[TraceparentHeaderName].FirstOrDefault();
        var incomingCustomTrace = context.Request.Headers[CustomTraceIdHeaderName].FirstOrDefault();

        var traceId = !string.IsNullOrWhiteSpace(incomingTraceparent)
            ? incomingTraceparent
            : !string.IsNullOrWhiteSpace(incomingCustomTrace)
                ? incomingCustomTrace
                : GenerateW3CTraceparent();

        context.Items["TraceId"] = traceId;
        context.TraceIdentifier = traceId;
        context.Response.Headers[TraceparentHeaderName] = traceId;
        context.Response.Headers[CustomTraceIdHeaderName] = traceId;

        await _next(context);
    }

    private static string GenerateW3CTraceparent()
    {
        var traceIdHex = Guid.NewGuid().ToString("N");
        var spanIdHex = Guid.NewGuid().ToString("N")[..16];
        return $"00-{traceIdHex}-{spanIdHex}-01";
    }
}
using Microsoft.Extensions.Options;
using Npgsql;
using OrdersService.Services;
using Instrumentation.Extensions;
using Instrumentation.Metrics;
using Instrumentation.Options;
using OrdersService.Faults;
using Instrumentation.Tracing;

var builder = WebApplication.CreateBuilder(args);

// Controllers
builder.Services.AddControllers();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();


var dbUrl = builder.Configuration["DATABASE_URL"]
    ?? throw new InvalidOperationException("DATABASE_URL is not set. Check your .env (Docker) or appsettings.Development.json (local).");

// Shared instrumentation
builder.Services.AddPlatformInstrumentation(dbUrl, options =>
{
    options.ServiceName = "orders-service";
    options.ServiceVersionProvider = () => FaultState.CurrentVersion;
});

// Business services
builder.Services.AddSingleton<CpuThrottleSimulator>();
builder.Services.AddSingleton<ConcurrencyLimitSimulator>();
builder.Services.AddScoped<OrderProcessor>();

var orderServicePort = builder.Configuration["ORDERS_SERVICE_PORT"] ?? "8081";
var orderServiceBaseUrl = $"http://localhost:{orderServicePort}";
builder.Services.AddSingleton(new TrafficGeneratorOptions { BaseUrl = orderServiceBaseUrl });


var paymentServiceHost = builder.Configuration["PAYMENTS_SERVICE_HOST"] ?? "localhost";
var paymentServicePort = builder.Configuration["PAYMENTS_SERVICE_PORT"] ?? "8082";
var paymentServiceBaseUrl = $"http://{paymentServiceHost}:{paymentServicePort}";
builder.Services.AddSingleton(new PaymentServiceOptions { BaseUrl = paymentServiceBaseUrl });
builder.Services.AddScoped<PaymentsProcessor>();

builder.Services.AddHttpClient();
builder.Services.AddHttpClient("payments-service", client => client.BaseAddress = new Uri(paymentServiceBaseUrl))
    .AddHttpMessageHandler<TraceIdPropagationHandler>();

builder.Services.AddHostedService<TrafficGeneratorService>();

// Metrics background worker
builder.Services.AddHostedService(sp =>
    new MetricsCollector(
        sp.GetRequiredService<NpgsqlDataSource>(),
        sp.GetRequiredService<RequestStats>(),
        sp.GetRequiredService<DbConnectionTracker>(),
        sp.GetRequiredService<IOptions<InstrumentationOptions>>()));

builder.Services.AddProblemDetails();

var app = builder.Build();

app.UseExceptionHandler();

app.UseSwagger();
app.UseSwaggerUI();

app.UsePlatformInstrumentation();

app.MapControllers();

app.Run();
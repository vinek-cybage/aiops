using Microsoft.Extensions.Options;
using Npgsql;
using PaymentsService.Faults;
using Instrumentation.Extensions;
using Instrumentation.Metrics;
using Instrumentation.Options;

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
    options.ServiceName = "payments-service";
    options.ServiceVersionProvider = () => FaultState.CurrentVersion;
});

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

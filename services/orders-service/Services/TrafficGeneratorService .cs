public class TrafficGeneratorService : BackgroundService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly TrafficGeneratorOptions _options;
    private readonly ILogger<TrafficGeneratorService> _logger;

    public TrafficGeneratorService(
        IHttpClientFactory httpClientFactory,
        TrafficGeneratorOptions options,
        ILogger<TrafficGeneratorService> logger)
    {
        _httpClientFactory = httpClientFactory;
        _options = options;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var client = _httpClientFactory.CreateClient();
        var random = new Random();

        while (!stoppingToken.IsCancellationRequested)
        {
            var batchSize = random.Next(2, 5); // up to 4 concurrent, per earlier decision
            var tasks = Enumerable.Range(0, batchSize)
                .Select(_ => random.Next(0, 2) == 0
                    ? SafeGet(client, $"{_options.BaseUrl}/orders/1", stoppingToken)
                    : SafePost(client, $"{_options.BaseUrl}/orders/1/checkout", stoppingToken));

            await Task.WhenAll(tasks);

            await Task.Delay(TimeSpan.FromMilliseconds(random.Next(300, 800)), stoppingToken);
        }
    }

    private async Task SafeGet(HttpClient client, string url, CancellationToken ct)
    {
        try
        {
            await client.GetAsync(url, ct);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Traffic generator GET request failed");
        }
    }

    private async Task SafePost(HttpClient client, string url, CancellationToken ct)
    {
        try
        {
            var payload = new { orderId = 1, amount = 249.99m };
            await client.PostAsJsonAsync(url, payload, ct);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Traffic generator POST request failed");
        }
    }

}
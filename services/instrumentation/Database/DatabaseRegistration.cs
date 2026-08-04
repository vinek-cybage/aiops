using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace Instrumentation.Database;

internal static class DatabaseRegistration
{
    internal static IServiceCollection AddDatabase(
        this IServiceCollection services,
        string connectionString)
    {
        var dataSource = new NpgsqlDataSourceBuilder(connectionString)
            .Build();

        services.AddSingleton(dataSource);

        return services;
    }
}
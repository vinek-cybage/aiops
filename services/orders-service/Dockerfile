# ---- Build stage ----
FROM docker.io/rijhwani/dotnet-sdk:10.0 AS build
WORKDIR /src

COPY ["services/orders-service/orders-service.csproj", "services/orders-service/"]
COPY ["services/instrumentation/instrumentation.csproj", "services/instrumentation/"]

RUN dotnet restore "services/orders-service/orders-service.csproj"

COPY services/orders-service/ services/orders-service/
COPY services/instrumentation/ services/instrumentation/

WORKDIR /src/services/orders-service
RUN dotnet publish -c Release -o /app --no-restore

# ---- Runtime stage ----
FROM docker.io/rijhwani/dotnet-aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app .

EXPOSE 8081
ENV ASPNETCORE_URLS=http://+:8081
ENV ORDERS_SERVICE_PORT=8081

ENTRYPOINT ["dotnet", "orders-service.dll"]
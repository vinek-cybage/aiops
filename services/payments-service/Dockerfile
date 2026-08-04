# ---- Build stage ----
FROM docker.io/rijhwani/dotnet-sdk:10.0 AS build
WORKDIR /src

COPY ["services/payments-service/payments-service.csproj", "services/payments-service/"]
COPY ["services/instrumentation/instrumentation.csproj", "services/instrumentation/"]

RUN dotnet restore "services/payments-service/payments-service.csproj"

COPY services/payments-service/ services/payments-service/
COPY services/instrumentation/ services/instrumentation/

WORKDIR /src/services/payments-service
RUN dotnet publish -c Release -o /app --no-restore

# ---- Runtime stage ----
FROM docker.io/rijhwani/dotnet-aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app .

EXPOSE 8082
ENV ASPNETCORE_URLS=http://+:8082
ENV PAYMENTS_SERVICE_PORT=8082

ENTRYPOINT ["dotnet", "payments-service.dll"]
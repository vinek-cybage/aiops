FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY telemetry-api/telemetry-api.csproj ./
RUN dotnet restore
COPY telemetry-api/ .
RUN dotnet publish -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "telemetry-api.dll"]

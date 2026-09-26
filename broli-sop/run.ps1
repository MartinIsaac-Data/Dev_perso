# Starts the API (http://localhost:5080) and the web portal (http://localhost:5090) for local use.
# Demo credentials are read from the environment; set them once per session, e.g.:
#   $env:Bootstrap__AdminPassword = "<choose one>"; $env:Demo__UserPassword = "<choose one>"
$ErrorActionPreference = "Stop"
if (-not $env:Bootstrap__AdminPassword) { Write-Warning "Bootstrap__AdminPassword not set: a random admin password will be printed in the API log." }
dotnet build Broli.SOP.sln
Start-Process dotnet -ArgumentList "run --no-build --project src/Broli.SOP.API --launch-profile http"
Start-Sleep -Seconds 5
dotnet run --no-build --project src/Broli.SOP.Web --launch-profile http

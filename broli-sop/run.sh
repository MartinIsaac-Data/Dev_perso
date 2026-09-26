#!/usr/bin/env bash
# Starts the API (http://localhost:5080) and the web portal (http://localhost:5090) for local use.
# Set Bootstrap__AdminPassword and Demo__UserPassword first, otherwise random passwords are printed in the API log.
set -euo pipefail
cd "$(dirname "$0")"
dotnet build Broli.SOP.sln
dotnet run --no-build --project src/Broli.SOP.API --launch-profile http &
API_PID=$!
trap 'kill $API_PID' EXIT
sleep 5
dotnet run --no-build --project src/Broli.SOP.Web --launch-profile http

<#
.SYNOPSIS
    Builds the Broli S&OP release package: API + portal published, SQL migration script, IIS install scripts.

.DESCRIPTION
    Runs on any machine with the .NET 10 SDK and PowerShell 7 (Windows, Linux, CI). Produces
    <Output>/broli-sop-<version>/ and the matching .zip, laid out as:

        api/                 Broli.SOP.API published (framework-dependent, needs the ASP.NET Core 10 Hosting Bundle)
        web/                 Broli.SOP.Web published
        sql/migrations.sql   idempotent script: safe to run on an empty or an up-to-date database
        sql/migrations.txt   migration ids contained in this release (the installer compares them with the installed ones)
        Install-BroliSop.ps1, Rollback-BroliSop.ps1, DEPLOYMENT.md, VERSION

    No configuration value or secret is written into the package: they are set on the server by the installer.

.EXAMPLE
    pwsh deploy/build-release.ps1
    pwsh deploy/build-release.ps1 -Version 1.0.0 -Output C:\releases
#>
[CmdletBinding()]
param(
    [string] $Output = (Join-Path $PSScriptRoot '..' 'release'),
    [string] $Version,
    [switch] $SkipTests
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-Step([string] $title, [scriptblock] $action) {
    Write-Host "==> $title" -ForegroundColor Cyan
    & $action
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$title failed (exit code $LASTEXITCODE)." }
}

if (-not $Version) {
    $sha = (git -C $root rev-parse --short HEAD 2>$null)
    $Version = '{0:yyyy.MM.dd}-{1}' -f (Get-Date), ($(if ($sha) { $sha } else { 'local' }))
}
$name = "broli-sop-$Version"
$package = Join-Path $Output $name
if (Test-Path $package) { Remove-Item $package -Recurse -Force }
New-Item -ItemType Directory -Force -Path $package, (Join-Path $package 'sql') | Out-Null

Push-Location $root
try {
    Invoke-Step 'Restore tools (dotnet-ef)' { dotnet tool restore }
    Invoke-Step 'Build (warnings are errors)' { dotnet build Broli.SOP.sln -c Release -warnaserror }
    if (-not $SkipTests) {
        Invoke-Step 'Tests' { dotnet test Broli.SOP.sln -c Release --no-build }
    }
    Invoke-Step 'Publish API' { dotnet publish src/Broli.SOP.API -c Release --no-build -o (Join-Path $package 'api') }
    Invoke-Step 'Publish portal' { dotnet publish src/Broli.SOP.Web -c Release --no-build -o (Join-Path $package 'web') }
    Invoke-Step 'SQL migration script (idempotent)' {
        dotnet tool run dotnet-ef migrations script --idempotent --project src/Broli.SOP.Data --no-build --configuration Release `
            -o (Join-Path $package 'sql' 'migrations.sql')
    }
    Invoke-Step 'Migration list' {
        $list = dotnet tool run dotnet-ef migrations list --no-connect --project src/Broli.SOP.Data --no-build --configuration Release
        if ($LASTEXITCODE -ne 0) { throw 'dotnet ef migrations list failed.' }
        # Keep only migration ids (yyyyMMddHHmmss_Name); the tool also prints build and info lines.
        $ids = @($list | Where-Object { $_ -match '^\d{14}_\w+' } | ForEach-Object { ($_ -split '\s')[0] })
        if ($ids.Count -eq 0) { throw 'No migration found: the package would not be able to create the database.' }
        Set-Content -Path (Join-Path $package 'sql' 'migrations.txt') -Value $ids -Encoding utf8
    }

    # Development settings and local databases must never reach a server.
    Get-ChildItem $package -Recurse -Include 'appsettings.Development.json', '*.db', '*.db-shm', '*.db-wal' | Remove-Item -Force

    Copy-Item (Join-Path $PSScriptRoot 'iis' '*') $package
    Copy-Item (Join-Path $root 'docs' 'DEPLOYMENT.md') $package
    Set-Content -Path (Join-Path $package 'VERSION') -Value $Version -Encoding utf8

    $zip = Join-Path $Output "$name.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $package '*') -DestinationPath $zip
    Write-Host "Package ready: $zip" -ForegroundColor Green
}
finally {
    Pop-Location
}

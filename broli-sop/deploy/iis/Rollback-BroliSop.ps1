<#
.SYNOPSIS
    Puts back a version saved by Install-BroliSop.ps1 (the most recent one by default).

.DESCRIPTION
    Stops the portal, moves the current version to backups\<timestamp>-rolled-back (so the rollback can itself be
    undone), restores the chosen backup, restarts and checks the API health. Settings are not changed.

    The database is not touched. If the version being removed had changed the schema, the older version runs on the
    newer schema; when that is not enough, restore the SQL Server backup taken before the update (DEPLOYMENT.md).

.EXAMPLE
    .\Rollback-BroliSop.ps1
    .\Rollback-BroliSop.ps1 -Backup C:\inetpub\broli-sop\backups\20261001-190455
#>
[CmdletBinding()]
param(
    [string] $InstallRoot = 'C:\inetpub\broli-sop',
    [string] $Backup,
    [int] $ApiPort = 5080
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'BroliSop.Iis.psm1') -Force

Assert-Administrator
$sm = Get-ServerManager

if (-not $Backup) {
    $latest = @(Get-Backups $InstallRoot | Where-Object { $_.Name -notlike '*-rolled-back' }) | Select-Object -First 1
    if ($null -eq $latest) { throw "No saved version in $InstallRoot\backups." }
    $Backup = $latest.FullName
}
if (-not (Test-Path (Join-Path $Backup 'api\Broli.SOP.API.dll'))) { throw "$Backup does not contain a saved version." }

$current = Get-InstalledVersion $InstallRoot
$target = Get-InstalledVersion $Backup
Write-Host "Rollback $current -> $target" -ForegroundColor Cyan

$dropped = @(Read-Migrations $InstallRoot | Where-Object { (Read-Migrations $Backup) -notcontains $_ })
if ($dropped.Count -gt 0) {
    Write-Warning ("The version being removed added database changes ($($dropped -join ', ')). They stay in the database. " +
                   'If the portal misbehaves after the rollback, restore the SQL backup taken before the update.')
}

Stop-BroliPools $sm
$saved = Save-CurrentVersion $InstallRoot '-rolled-back'
foreach ($item in @('api', 'web', 'sql', 'VERSION')) {
    $path = Join-Path $Backup $item
    if (Test-Path $path) { Move-Item $path $InstallRoot }
}
Remove-Item $Backup -Recurse -Force
Start-BroliPools (New-Object Microsoft.Web.Administration.ServerManager)

if (-not (Wait-ApiHealthy $ApiPort)) {
    throw "Version $target restored but the API does not answer. Removed version kept in $saved. See Event Viewer > Application."
}
Write-Host "Version $target is running. The removed version is kept in $saved." -ForegroundColor Green

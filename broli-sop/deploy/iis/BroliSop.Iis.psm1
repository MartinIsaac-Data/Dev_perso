# Shared helpers for Install-BroliSop.ps1 and Rollback-BroliSop.ps1.
# Windows PowerShell 5.1 compatible (the default shell on Windows Server): no PowerShell 7-only syntax.

Set-StrictMode -Version Latest

$script:ApiPool = 'BroliSOP-API'
$script:WebPool = 'BroliSOP-Web'
$script:ApiSite = 'BroliSOP-API'
$script:WebSite = 'BroliSOP'

function Get-BroliNames {
    [pscustomobject]@{ ApiPool = $script:ApiPool; WebPool = $script:WebPool; ApiSite = $script:ApiSite; WebSite = $script:WebSite }
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated PowerShell (Run as administrator).'
    }
}

function Get-ServerManager {
    $dll = Join-Path $env:windir 'system32\inetsrv\Microsoft.Web.Administration.dll'
    if (-not (Test-Path $dll)) { throw 'IIS is not installed (Microsoft.Web.Administration.dll not found).' }
    Add-Type -Path $dll
    return New-Object Microsoft.Web.Administration.ServerManager
}

function Test-GlobalModule($sm, [string] $name) {
    $modules = $sm.GetApplicationHostConfiguration().GetSection('system.webServer/globalModules').GetCollection()
    foreach ($m in $modules) { if ($m['name'] -eq $name) { return $true } }
    return $false
}

function Get-PoolVariable($pool, [string] $name) {
    foreach ($e in $pool.GetChildElement('environmentVariables').GetCollection()) {
        if ($e['name'] -eq $name) { return [string] $e['value'] }
    }
    return $null
}

# Environment variables are stored on the application pool (applicationHost.config, outside the web folders),
# never in the published files. A $null value removes the variable.
function Set-PoolVariable($pool, [string] $name, $value) {
    $collection = $pool.GetChildElement('environmentVariables').GetCollection()
    $existing = $null
    foreach ($e in $collection) { if ($e['name'] -eq $name) { $existing = $e } }
    if ($null -ne $existing) { $collection.Remove($existing) }
    if ($null -ne $value) {
        $element = $collection.CreateElement('add')
        $element['name'] = $name
        $element['value'] = [string] $value
        $collection.Add($element) | Out-Null
    }
}

function Stop-BroliPools($sm) {
    foreach ($name in @($script:WebPool, $script:ApiPool)) {
        $pool = $sm.ApplicationPools[$name]
        if ($null -eq $pool) { continue }
        if ($pool.State -ne 'Stopped') {
            Write-Host "   stopping $name"
            $pool.Stop() | Out-Null
        }
        $deadline = (Get-Date).AddSeconds(60)
        while ($pool.WorkerProcesses.Count -gt 0 -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
            $sm = New-Object Microsoft.Web.Administration.ServerManager
            $pool = $sm.ApplicationPools[$name]
        }
    }
    Start-Sleep -Seconds 2   # let the ASP.NET Core module release file handles
}

function Start-BroliPools($sm) {
    foreach ($name in @($script:ApiPool, $script:WebPool)) {
        $pool = $sm.ApplicationPools[$name]
        if ($null -ne $pool -and $pool.State -ne 'Started') { $pool.Start() | Out-Null }
    }
    foreach ($name in @($script:ApiSite, $script:WebSite)) {
        $site = $sm.Sites[$name]
        if ($null -ne $site -and $site.State -ne 'Started') { $site.Start() | Out-Null }
    }
}

# The API answers /health once the database is migrated and seeded; the first start can take a while.
function Wait-ApiHealthy([int] $port, [int] $timeoutSeconds = 180) {
    $url = "http://127.0.0.1:$port/health"
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
            if ($r.StatusCode -eq 200) { return $true }
        }
        catch { Start-Sleep -Seconds 3 }
    }
    return $false
}

function Read-Migrations([string] $folder) {
    $file = Join-Path $folder 'sql\migrations.txt'
    if (-not (Test-Path $file)) { return @() }
    return @(Get-Content $file | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
}

function Get-Backups([string] $installRoot) {
    $dir = Join-Path $installRoot 'backups'
    if (-not (Test-Path $dir)) { return @() }
    return @(Get-ChildItem $dir -Directory | Sort-Object Name -Descending)
}

# Moves the installed version (api, web, sql, VERSION) into backups\<timestamp>; returns that folder.
function Save-CurrentVersion([string] $installRoot, [string] $suffix = '') {
    if (-not (Test-Path (Join-Path $installRoot 'api'))) { return $null }
    $target = Join-Path (Join-Path $installRoot 'backups') ((Get-Date -Format 'yyyyMMdd-HHmmss') + $suffix)
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    foreach ($item in @('api', 'web', 'sql', 'VERSION')) {
        $path = Join-Path $installRoot $item
        if (Test-Path $path) { Move-Item $path $target }
    }
    return $target
}

function Restore-Version([string] $installRoot, [string] $backup) {
    foreach ($item in @('api', 'web', 'sql', 'VERSION')) {
        $current = Join-Path $installRoot $item
        if (Test-Path $current) { Remove-Item $current -Recurse -Force }
        $saved = Join-Path $backup $item
        if (Test-Path $saved) { Move-Item $saved $installRoot }
    }
    Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue
}

function Get-InstalledVersion([string] $installRoot) {
    $file = Join-Path $installRoot 'VERSION'
    if (Test-Path $file) { return (Get-Content $file -TotalCount 1).Trim() }
    return '(unknown)'
}

Export-ModuleMember -Function *

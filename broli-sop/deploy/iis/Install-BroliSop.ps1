<#
.SYNOPSIS
    Installs or updates the Broli S&OP portal on IIS (Windows Server). Run from the unzipped release package.

.DESCRIPTION
    First install: creates two application pools and two sites.
      - BroliSOP-API  listens on 127.0.0.1:<ApiPort> only (not reachable from the network; the portal calls it locally).
      - BroliSOP      the portal, on HTTPS (certificate thumbprint) or HTTP.
    Update: stops the pools, moves the installed version to backups\<timestamp>, copies the new one, restarts,
    and checks the API health. If the API does not come back, the previous version is restored automatically.

    Settings and secrets are stored as environment variables of the application pools (applicationHost.config),
    never in the published files. The database connection uses Windows authentication with the pool identity
    by default (no password stored); -SqlCredential switches to a SQL login. The JWT signing key is generated on
    the first install and kept on updates. The administrator password is asked once, checked by signing in,
    then removed from the configuration.

    See DEPLOYMENT.md for the prerequisites and the database rights to grant.

.EXAMPLE
    # First install, HTTPS, database migrated by the application
    .\Install-BroliSop.ps1 -SqlServer SQLPROD01 -HostName sop.broli.local -CertificateThumbprint 3F2A...

.EXAMPLE
    # First install with SQL Server on the same machine: also create the database and grant the pool identity access
    .\Install-BroliSop.ps1 -SqlServer .\SQLEXPRESS -HostName sop.broli.local -CertificateThumbprint 3F2A... -GrantDatabaseAccess

.EXAMPLE
    # Update: all settings are kept
    .\Install-BroliSop.ps1

.EXAMPLE
    # First install where the DBA runs sql\migrations.sql and the application only reads/writes data
    .\Install-BroliSop.ps1 -SqlServer SQLPROD01 -HostName sop.broli.local -CertificateThumbprint 3F2A... -DbaAppliesMigrations
#>
[CmdletBinding()]
param(
    [string] $PackagePath = $PSScriptRoot,
    [string] $InstallRoot = 'C:\inetpub\broli-sop',
    [string] $SqlServer,
    [string] $Database = 'BroliSOP',
    [pscredential] $SqlCredential,
    [string] $HostName,
    [string] $CertificateThumbprint,
    [int] $WebPort = 0,
    [int] $ApiPort = 5080,
    [switch] $DbaAppliesMigrations,
    [switch] $GrantDatabaseAccess,
    [switch] $SchemaUpdatedByDba,
    [switch] $SqlBackupDone,
    [string] $InboxRoot,
    [int] $KeepBackups = 3,
    # Unattended first install only (otherwise the password is asked twice on screen).
    [securestring] $AdminPassword
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'BroliSop.Iis.psm1') -Force
$names = Get-BroliNames

function Step([string] $text) { Write-Host "==> $text" -ForegroundColor Cyan }

function ConvertTo-Plain([securestring] $secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# ---------------------------------------------------------------- checks (nothing is changed before this block passes)
Step 'Checks'
Assert-Administrator
$sm = Get-ServerManager
if (-not (Test-GlobalModule $sm 'AspNetCoreModuleV2')) {
    throw 'ASP.NET Core Hosting Bundle 10 is not installed (IIS module AspNetCoreModuleV2 missing). Install it, then run iisreset.'
}
if (-not (Test-GlobalModule $sm 'WebSocketModule')) {
    throw 'IIS WebSocket Protocol is not installed; the portal needs it. Install-WindowsFeature Web-WebSockets'
}
if (-not (Test-GlobalModule $sm 'ApplicationInitializationModule')) {
    Write-Warning 'IIS Application Initialization is not installed: the API will only start on its first request. Install-WindowsFeature Web-AppInit'
}
foreach ($required in @('api\Broli.SOP.API.dll', 'web\Broli.SOP.Web.dll', 'sql\migrations.sql', 'sql\migrations.txt', 'VERSION')) {
    if (-not (Test-Path (Join-Path $PackagePath $required))) { throw "Incomplete package: $required missing in $PackagePath." }
}
$newVersion = (Get-Content (Join-Path $PackagePath 'VERSION') -TotalCount 1).Trim()

$apiPoolExisting = $sm.ApplicationPools[$names.ApiPool]
$firstInstall = $null -eq $apiPoolExisting -or -not (Test-Path (Join-Path $InstallRoot 'api'))
if ($firstInstall) {
    if (-not $SqlServer) { throw 'First install: -SqlServer is required.' }
    if (-not $HostName) { throw 'First install: -HostName is required (the name users type, e.g. sop.broli.local).' }
    if (-not $CertificateThumbprint) {
        Write-Warning 'No -CertificateThumbprint: the portal will use plain HTTP. Use HTTPS in production (passwords travel on sign-in).'
    }
}

$applyMigrations = 'true'
if ($DbaAppliesMigrations) { $applyMigrations = 'false' }
elseif (-not $firstInstall) {
    $existing = Get-PoolVariable $apiPoolExisting 'Database__ApplyMigrations'
    if ($existing) { $applyMigrations = $existing }
}

# Schema changes: the application cannot be rolled back past a migrated database without restoring a SQL backup.
$installed = Read-Migrations $InstallRoot
$incoming = Read-Migrations $PackagePath
$newMigrations = @($incoming | Where-Object { $installed -notcontains $_ })
if (-not $firstInstall -and $newMigrations.Count -gt 0) {
    Write-Host "   This release changes the database schema: $($newMigrations -join ', ')" -ForegroundColor Yellow
    if ($applyMigrations -eq 'false' -and -not $SchemaUpdatedByDba) {
        throw ("The DBA applies migrations on this server: have sql\migrations.sql from this package run on [$Database] " +
               'first, then run this script again with -SchemaUpdatedByDba. Nothing has been changed.')
    }
    if (-not $SqlBackupDone) {
        throw ('Take a SQL Server backup of the database first (the new version updates its schema on start), ' +
               'then run this script again with -SqlBackupDone. Nothing has been changed.')
    }
}
if ($firstInstall -and $applyMigrations -eq 'false' -and -not $SchemaUpdatedByDba) {
    throw ("-DbaAppliesMigrations: have sql\migrations.sql from this package run on [$Database] first " +
           '(it creates the schema), then run this script again with -SchemaUpdatedByDba.')
}

$adminPassword = $null
if ($firstInstall) {
    if ($AdminPassword) {
        $adminPassword = ConvertTo-Plain $AdminPassword
    }
    else {
        $adminPassword = ConvertTo-Plain (Read-Host 'Password for the first administrator account "admin" (min. 8 characters)' -AsSecureString)
        $again = ConvertTo-Plain (Read-Host 'Type it again' -AsSecureString)
        if ($again -cne $adminPassword) { throw 'The two passwords differ. Nothing has been changed.' }
    }
    if ($adminPassword.Length -lt 8) { throw 'The administrator password must have at least 8 characters.' }
}

Write-Host ("   {0} {1} -> {2}" -f $(if ($firstInstall) { 'Install' } else { 'Update' }), (Get-InstalledVersion $InstallRoot), $newVersion)

# ---------------------------------------------------------------- files
Step 'Stopping the portal'
Stop-BroliPools $sm

Step 'Saving the installed version'
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$backup = Save-CurrentVersion $InstallRoot
if ($backup) { Write-Host "   saved to $backup" }

Step 'Copying the new version'
foreach ($item in @('api', 'web', 'sql', 'VERSION')) {
    Copy-Item (Join-Path $PackagePath $item) $InstallRoot -Recurse -Force
}
$apiPath = Join-Path $InstallRoot 'api'
$webPath = Join-Path $InstallRoot 'web'

# ---------------------------------------------------------------- IIS configuration (idempotent)
Step 'Configuring IIS'
$sm = New-Object Microsoft.Web.Administration.ServerManager
foreach ($poolName in @($names.ApiPool, $names.WebPool)) {
    $pool = $sm.ApplicationPools[$poolName]
    if ($null -eq $pool) { $pool = $sm.ApplicationPools.Add($poolName) }
    $pool.ManagedRuntimeVersion = ''                      # ASP.NET Core runs its own runtime
    $pool.StartMode = 'AlwaysRunning'                     # the scheduler and the cache warm-up need a live process
    $pool.ProcessModel.IdleTimeout = [TimeSpan]::Zero
    $pool.ProcessModel.LoadUserProfile = $true            # keeps the portal's session keys across restarts
    $pool.Recycling.PeriodicRestart.Time = [TimeSpan]::Zero
    $pool.Recycling.PeriodicRestart.Schedule.Clear()
    $pool.Recycling.PeriodicRestart.Schedule.Add([TimeSpan]::FromHours(3)) | Out-Null   # nightly, outside working hours
}

$apiSite = $sm.Sites[$names.ApiSite]
if ($null -eq $apiSite) {
    $apiSite = $sm.Sites.Add($names.ApiSite, 'http', "127.0.0.1:${ApiPort}:", $apiPath)
}
$apiSite.Applications['/'].ApplicationPoolName = $names.ApiPool
$apiSite.Applications['/'].VirtualDirectories['/'].PhysicalPath = $apiPath
$apiSite.Applications['/']['preloadEnabled'] = $true

$webSite = $sm.Sites[$names.WebSite]
if ($null -eq $webSite -or $HostName -or $CertificateThumbprint) {
    if ($null -ne $webSite) {
        if (-not $HostName) { $HostName = $webSite.Bindings[0].Host }   # changing only the certificate keeps the name
        $sm.Sites.Remove($webSite)
    }
    if ($CertificateThumbprint) {
        $thumb = ($CertificateThumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
        if (-not (Test-Path "Cert:\LocalMachine\My\$thumb")) { throw "Certificate $thumb not found in LocalMachine\My." }
        if (-not $HostName) { throw 'HTTPS needs -HostName (the name on the certificate).' }
        $port = $(if ($WebPort -gt 0) { $WebPort } else { 443 })
        $hash = New-Object byte[] ($thumb.Length / 2)
        for ($i = 0; $i -lt $hash.Length; $i++) { $hash[$i] = [Convert]::ToByte($thumb.Substring($i * 2, 2), 16) }
        $webSite = $sm.Sites.Add($names.WebSite, "*:${port}:$HostName", $webPath, $hash, 'My')
        $webSite.Bindings[0].SetAttributeValue('sslFlags', 1)   # SNI: several HTTPS sites can share the server
    }
    else {
        $port = $(if ($WebPort -gt 0) { $WebPort } else { 80 })
        $webSite = $sm.Sites.Add($names.WebSite, 'http', "*:${port}:$HostName", $webPath)
    }
}
$webSite.Applications['/'].ApplicationPoolName = $names.WebPool
$webSite.Applications['/'].VirtualDirectories['/'].PhysicalPath = $webPath

# ---------------------------------------------------------------- settings (environment variables of the pools)
$apiPool = $sm.ApplicationPools[$names.ApiPool]
$webPool = $sm.ApplicationPools[$names.WebPool]
Set-PoolVariable $apiPool 'ASPNETCORE_ENVIRONMENT' 'Production'
Set-PoolVariable $apiPool 'Database__Provider' 'SqlServer'
Set-PoolVariable $apiPool 'Database__ApplyMigrations' $applyMigrations
if ($SqlServer) {
    $cs = "Server=$SqlServer;Database=$Database;Encrypt=True;TrustServerCertificate=True;Application Name=Broli S&OP"
    if ($SqlCredential) {
        $cs += ";User ID=$($SqlCredential.UserName);Password=$($SqlCredential.GetNetworkCredential().Password)"
    }
    else {
        $cs += ';Integrated Security=True'
    }
    Set-PoolVariable $apiPool 'ConnectionStrings__Sop' $cs
}
if (-not (Get-PoolVariable $apiPool 'Jwt__Key')) {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    Set-PoolVariable $apiPool 'Jwt__Key' ([Convert]::ToBase64String($bytes))
}
if ($InboxRoot) { Set-PoolVariable $apiPool 'DataSources__InboxRoot' $InboxRoot }
if ($adminPassword) {
    Set-PoolVariable $apiPool 'Bootstrap__AdminUsername' 'admin'
    Set-PoolVariable $apiPool 'Bootstrap__AdminPassword' $adminPassword
}
Set-PoolVariable $webPool 'ASPNETCORE_ENVIRONMENT' 'Production'
Set-PoolVariable $webPool 'Api__BaseUrl' "http://127.0.0.1:$ApiPort/"
$sm.CommitChanges()

# Folder rights for the pool identities (inherit to files and sub-folders).
& icacls $apiPath /grant "IIS AppPool\$($names.ApiPool):(OI)(CI)RX" /T /Q | Out-Null
& icacls $webPath /grant "IIS AppPool\$($names.WebPool):(OI)(CI)RX" /T /Q | Out-Null
if ($InboxRoot) {
    New-Item -ItemType Directory -Force -Path $InboxRoot | Out-Null
    & icacls $InboxRoot /grant "IIS AppPool\$($names.ApiPool):(OI)(CI)M" /T /Q | Out-Null
}

# The pool's virtual account exists only now that the pool does: SQL access for it can be granted from this point.
if ($GrantDatabaseAccess) {
    if (-not $SqlServer) { throw '-GrantDatabaseAccess needs -SqlServer.' }
    if ($SqlCredential) { throw '-GrantDatabaseAccess sets up Windows authentication; do not combine it with -SqlCredential.' }
    Step 'Granting database access'
    Grant-DatabaseAccess $SqlServer $Database ($applyMigrations -eq 'true')
}

# ---------------------------------------------------------------- start and verify
Step 'Starting'
try {
    $sm = New-Object Microsoft.Web.Administration.ServerManager
    Start-BroliPools $sm
    if (-not (Wait-ApiHealthy $ApiPort)) {
        $hint = 'Details: Event Viewer > Windows Logs > Application (sources "IIS AspNetCore Module V2" and ".NET Runtime").'
        if ($backup) {
            Write-Warning 'The API did not start: restoring the previous version.'
            Stop-BroliPools $sm
            Restore-Version $InstallRoot $backup
            Start-BroliPools (New-Object Microsoft.Web.Administration.ServerManager)
            $restored = Wait-ApiHealthy $ApiPort
            throw ("Update failed; previous version restored ({0}). {1}" -f $(if ($restored) { 'running' } else { 'NOT responding either' }), $hint)
        }
        throw ("The API did not start. Check that SQL Server is reachable and that {0} has access to [{1}] " +
           "(DEPLOYMENT.md, step 2, or rerun with -GrantDatabaseAccess). {2}") -f (Get-ApiSqlPrincipal $SqlServer), $Database, $hint
    }
    Write-Host '   API healthy'

    if ($adminPassword) {
        Step 'Checking the administrator account'
        $body = @{ username = 'admin'; password = $adminPassword } | ConvertTo-Json
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/api/auth/login" -Method Post -Body $body -ContentType 'application/json' -UseBasicParsing | Out-Null
            Write-Host '   sign-in OK'
        }
        catch {
            Write-Warning "Sign-in as admin failed ($($_.Exception.Message)). An administrator may already exist in this database."
        }
    }
}
finally {
    if ($adminPassword) {
        # Only needed to create the account: never leave the password in the server configuration, even after a failure.
        $sm = New-Object Microsoft.Web.Administration.ServerManager
        Set-PoolVariable $sm.ApplicationPools[$names.ApiPool] 'Bootstrap__AdminPassword' $null
        $sm.CommitChanges()
        $adminPassword = $null
    }
}

# ---------------------------------------------------------------- tidy up
$old = @(Get-Backups $InstallRoot | Select-Object -Skip $KeepBackups)
foreach ($dir in $old) { Remove-Item $dir.FullName -Recurse -Force }

$sm = New-Object Microsoft.Web.Administration.ServerManager
$binding = $sm.Sites[$names.WebSite].Bindings[0]
$url = '{0}://{1}{2}/' -f $binding.Protocol, $(if ($binding.Host) { $binding.Host } else { $env:COMPUTERNAME }),
    $(if (($binding.Protocol -eq 'https' -and $binding.EndPoint.Port -eq 443) -or ($binding.Protocol -eq 'http' -and $binding.EndPoint.Port -eq 80)) { '' } else { ":$($binding.EndPoint.Port)" })
Write-Host ''
Write-Host "Broli S&OP $newVersion is running: $url" -ForegroundColor Green
if ($backup) { Write-Host "Previous version kept in $backup (Rollback-BroliSop.ps1 restores it)." }

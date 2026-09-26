<#
    CI only (Windows runner with IIS, the Hosting Bundle and SQL Server Express already installed).
    Runs the documented procedure end to end with Windows PowerShell 5.1:
      1. first install over HTTPS (self-signed certificate), database created and the pool identity granted access
         (-GrantDatabaseAccess), Windows authentication without any stored password;
      2. update to a new version: backup kept, portal healthy;
      3. broken update: the installer must restore the previous version by itself;
      4. manual rollback with Rollback-BroliSop.ps1.
    After each step: API healthy on 127.0.0.1 only, portal served over HTTPS, no password left in applicationHost.config.
#>
param(
    [Parameter(Mandatory)] [string] $Package,
    [string] $SqlServer = '.\SQLEXPRESS'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = 'C:\inetpub\broli-sop'
$config = Join-Path $env:windir 'system32\inetsrv\config\applicationHost.config'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Check([string] $what, [scriptblock] $test) {
    if (-not (& $test)) { throw "FAILED: $what" }
    Write-Host "  ok - $what" -ForegroundColor Green
}

function Test-Status([string] $url, [int] $expected = 200) {
    try { return (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 30).StatusCode -eq $expected }
    catch { return $false }
}

function Assert-Running([string] $version) {
    Check "API healthy on 127.0.0.1:5080" { Test-Status 'http://127.0.0.1:5080/health' }
    $lan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1).IPAddress
    Check "API not reachable from the network ($lan)" { -not (Test-Status "http://${lan}:5080/health") }
    Check 'portal served over HTTPS' {
        try {
            $r = Invoke-WebRequest 'https://localhost/login' -UseBasicParsing -TimeoutSec 60
            $r.StatusCode -eq 200 -and $r.Content -match 'blazor'
        }
        catch {
            # Show the whole chain: the outer message of a TLS failure ("unexpected error on a send") hides the cause.
            $e = $_.Exception
            while ($null -ne $e) { Write-Host "    $($e.GetType().Name): $($e.Message)"; $e = $e.InnerException }
            $false
        }
    }
    Check "installed version is $version" { (Get-Content (Join-Path $root 'VERSION') -TotalCount 1).Trim() -eq $version }
    Check 'no administrator password left in applicationHost.config' { -not (Select-String -Path $config -Pattern 'Bootstrap__AdminPassword' -Quiet) }
    Check 'JWT key generated and stored on the API pool' { Select-String -Path $config -Pattern 'Jwt__Key' -Quiet }
}

function New-PackageVersion([string] $version) {
    $copy = Join-Path $env:RUNNER_TEMP "pkg-$version"
    if (Test-Path $copy) { Remove-Item $copy -Recurse -Force }
    Copy-Item $Package $copy -Recurse
    Set-Content (Join-Path $copy 'VERSION') $version
    return $copy
}

$cert = New-SelfSignedCertificate -DnsName 'localhost' -CertStoreLocation 'Cert:\LocalMachine\My'
# Trusted like a corporate CA certificate would be on the users' machines (no validation bypass in the test client).
$rootStore = New-Object Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
$rootStore.Open('ReadWrite'); $rootStore.Add($cert); $rootStore.Close()
$password = 'Ci-' + [Guid]::NewGuid().ToString('N').Substring(0, 16)
$v1 = New-PackageVersion '1.0.0'
$v2 = New-PackageVersion '1.1.0'
$broken = New-PackageVersion '1.2.0-broken'
Set-Content (Join-Path $broken 'api\appsettings.json') '{ this is not json'

Write-Host '== 1. First install'
& (Join-Path $v1 'Install-BroliSop.ps1') -SqlServer $SqlServer -HostName 'localhost' -CertificateThumbprint $cert.Thumbprint `
    -GrantDatabaseAccess -AdminPassword (ConvertTo-SecureString $password -AsPlainText -Force)
Assert-Running '1.0.0'
Check 'admin can sign in with the password given at install' {
    $body = @{ username = 'admin'; password = $password } | ConvertTo-Json
    (Invoke-WebRequest 'http://127.0.0.1:5080/api/auth/login' -Method Post -Body $body -ContentType 'application/json' -UseBasicParsing).StatusCode -eq 200
}
Check 'SQL connection uses Windows authentication (no password stored)' {
    $line = Select-String -Path $config -Pattern 'ConnectionStrings__Sop' -SimpleMatch | Select-Object -First 1
    $null -ne $line -and $line.Line -match 'Integrated Security=True' -and $line.Line -notmatch 'Password='
}

Write-Host '== 2. Update'
& (Join-Path $v2 'Install-BroliSop.ps1')
Assert-Running '1.1.0'
Check 'previous version kept in backups' { @(Get-ChildItem (Join-Path $root 'backups') -Directory).Count -ge 1 }

Write-Host '== 3. Broken update: automatic restore'
$failed = $false
try { & (Join-Path $broken 'Install-BroliSop.ps1') }
catch {
    $failed = $true
    $message = $_.Exception.Message
    Write-Host "  installer reported: $message"
    Check 'installer says the previous version was restored and runs' { $message -match 'previous version restored \(running\)' }
}
Check 'broken update was refused' { $failed }
Assert-Running '1.1.0'

Write-Host '== 4. Manual rollback'
& (Join-Path $v2 'Rollback-BroliSop.ps1')
Assert-Running '1.0.0'

Write-Host 'IIS deployment verified.' -ForegroundColor Green

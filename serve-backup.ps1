<#
.SYNOPSIS
    Serve the Antaera Wiki from this machine when the live site is unavailable.

.DESCRIPTION
    Disaster-recovery entry point. Rebuilds the site from the Markdown in this
    folder and serves it over the local network, with no dependency on GitHub,
    Cloudflare, or any external service. Bootstraps the Python environment if
    it is missing, so this works on a machine that has never run the wiki.

.PARAMETER Port
    Port to listen on. Defaults to 8000.

.PARAMETER LocalOnly
    Bind to 127.0.0.1 instead of all interfaces. Use when you do not want other
    devices on the network to reach it.
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$LocalOnly
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'No virtual environment found - bootstrapping.' -ForegroundColor Yellow

    $system = Get-Command python -ErrorAction SilentlyContinue
    if (-not $system) {
        throw 'Python is not installed. Install Python 3.10+ and re-run this script.'
    }

    & $system.Source -m venv .venv
    & $python -m pip install --quiet --upgrade pip
}

Write-Host 'Installing dependencies...' -ForegroundColor Cyan
& $python -m pip install --quiet -r requirements.txt

Write-Host 'Building site...' -ForegroundColor Cyan
& $python -m mkdocs build
if ($LASTEXITCODE -ne 0) { throw 'Build failed. The Markdown source may be damaged.' }

$bind = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }

Write-Host ''
Write-Host 'Backup wiki is up.' -ForegroundColor Green
Write-Host "  This machine : http://localhost:$Port/"

if (-not $LocalOnly) {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.InterfaceAlias -notlike '*vEthernet*' -and
            $_.InterfaceAlias -notlike '*WSL*' -and
            $_.InterfaceAlias -notlike '*Loopback*'
        } |
        ForEach-Object { Write-Host "  Other devices: http://$($_.IPAddress):$Port/" }

    Write-Host ''
    Write-Host 'If other devices cannot connect, Windows Firewall is blocking the port.' -ForegroundColor Yellow
    Write-Host 'Open it with (run as Administrator):' -ForegroundColor Yellow
    Write-Host "  New-NetFirewallRule -DisplayName 'Antaera Wiki backup' -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow -Profile Private" -ForegroundColor DarkGray
}

Write-Host ''
Write-Host 'Press Ctrl+C to stop.' -ForegroundColor DarkGray
Write-Host ''

& $python -m http.server $Port --bind $bind --directory site

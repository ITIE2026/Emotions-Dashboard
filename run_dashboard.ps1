[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$AppRoot = Join-Path $RepoRoot "Emotions-Dashboard\bci_dashboard"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$MainPath = Join-Path $AppRoot "main.py"
$RequiredBranch = "master"
$WebView2Guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

function Get-CurrentBranch {
    if ($env:BCI_DASHBOARD_TEST_BRANCH) {
        return $env:BCI_DASHBOARD_TEST_BRANCH
    }

    try {
        return (git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
    } catch {
        return ""
    }
}

function Assert-SupportedBranch {
    $branch = Get-CurrentBranch
    if (-not $branch) {
        throw "Unable to determine the current git branch. Run this script from the repository root checkout."
    }
    if ($branch -ne $RequiredBranch) {
        throw "This dashboard must run from the '$RequiredBranch' branch. Current branch: '$branch'. Run: git checkout $RequiredBranch ; git pull origin $RequiredBranch"
    }
}

function Assert-Venv {
    if (-not (Test-Path $VenvPython)) {
        throw "Repo virtual environment is missing at '$VenvPython'. Run .\setup_windows.ps1 first."
    }

    $versionScript = "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))"
    $version = (& $VenvPython -c $versionScript).Trim()
    if ($version -ne "3.11") {
        throw "Repo virtual environment is not using Python 3.11. Run .\setup_windows.ps1 to rebuild it."
    }
}

function Get-WebView2Version {
    if ($null -ne $env:BCI_DASHBOARD_TEST_WEBVIEW2_VERSION) {
        if ([string]::IsNullOrWhiteSpace($env:BCI_DASHBOARD_TEST_WEBVIEW2_VERSION)) {
            return $null
        }
        return $env:BCI_DASHBOARD_TEST_WEBVIEW2_VERSION
    }

    $paths = @(
        "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$WebView2Guid",
        "HKLM:\Software\Microsoft\EdgeUpdate\Clients\$WebView2Guid",
        "HKLM:\Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\$WebView2Guid"
    )

    foreach ($path in $paths) {
        try {
            $value = (Get-ItemProperty -Path $path -Name pv -ErrorAction Stop).pv
            if ($value -and $value -ne "0.0.0.0") {
                return [string]$value
            }
        } catch {
        }
    }

    return $null
}

function Assert-WebView2Runtime {
    if (-not (Get-WebView2Version)) {
        throw "Microsoft Edge WebView2 Runtime is missing. Run .\setup_windows.ps1 before launching the dashboard."
    }
}

function Assert-PythonRuntime {
    $checkScript = @'
import importlib
import pathlib
import sys

repo_root = pathlib.Path(r'''__REPO_ROOT__''')
host_script = repo_root / 'Emotions-Dashboard' / 'bci_dashboard' / 'gui' / '_wv2_host.py'
issues = []

if not host_script.is_file():
    issues.append(f'Missing host script: {host_script}')

for module_name, label in (('webview', 'pywebview'), ('pythonnet', 'pythonnet')):
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        issues.append(f'{label}: {exc}')

if issues:
    for issue in issues:
        print(issue)
    raise SystemExit(1)
'@
    $checkScript = $checkScript.Replace("__REPO_ROOT__", $RepoRoot)

    & $VenvPython -c $checkScript
    if ($LASTEXITCODE -ne 0) {
        throw "Repo virtual environment is missing required Instagram dependencies. Run .\setup_windows.ps1 first."
    }
}

$scriptExitCode = 0

try {
    Push-Location $RepoRoot
    Assert-SupportedBranch
    if (-not (Test-Path $MainPath)) {
        throw "Dashboard entry point is missing: '$MainPath'"
    }
    Assert-Venv
    Assert-WebView2Runtime
    Assert-PythonRuntime

    if ($DryRun) {
        Write-Output "RUN_DASHBOARD_READY"
    } else {
        & $VenvPython $MainPath
        $scriptExitCode = $LASTEXITCODE
    }
} finally {
    Pop-Location
}

exit $scriptExitCode

[CmdletBinding()]
param(
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$AppRoot = Join-Path $RepoRoot "Emotions-Dashboard\bci_dashboard"
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsPath = Join-Path $AppRoot "requirements.txt"
$MainPath = Join-Path $AppRoot "main.py"
$CapsuleDll = Join-Path $AppRoot "lib\CapsuleClient.dll"
$CapsuleSdkDir = Join-Path $AppRoot "capsule_sdk"
$HostScript = Join-Path $AppRoot "gui\_wv2_host.py"
$RequiredBranch = "master"
$WebView2Guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

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
        throw "This dashboard must be set up from the '$RequiredBranch' branch. Current branch: '$branch'. Run: git checkout $RequiredBranch ; git pull origin $RequiredBranch"
    }
}

function New-PythonSpec([string]$Exe, [string[]]$Args = @()) {
    return [pscustomobject]@{
        Exe = $Exe
        Args = $Args
    }
}

function Get-PythonVersion($Spec) {
    $versionScript = "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))"
    $baseArgs = @()
    if ($null -ne $Spec.Args) {
        $baseArgs = @($Spec.Args)
    }

    if ($baseArgs.Count -gt 0) {
        return ((& $Spec.Exe @baseArgs -c $versionScript) | Select-Object -First 1).Trim()
    }

    return ((& $Spec.Exe -c $versionScript) | Select-Object -First 1).Trim()
}

function Get-Python311Spec {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $spec = New-PythonSpec "py" @("-3.11")
        try {
            if ((Get-PythonVersion $spec) -eq "3.11") {
                return $spec
            }
        } catch {
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $spec = New-PythonSpec "python"
        try {
            if ((Get-PythonVersion $spec) -eq "3.11") {
                return $spec
            }
        } catch {
        }
    }

    throw "Python 3.11 is required. Install Python 3.11, then rerun .\setup_windows.ps1."
}

function Ensure-Venv {
    if ($CheckOnly) {
        if (-not (Test-Path $VenvPython)) {
            throw "The repo virtual environment is missing at '$VenvDir'. Run .\setup_windows.ps1 without -CheckOnly."
        }
        $venvSpec = New-PythonSpec $VenvPython
        if ((Get-PythonVersion $venvSpec) -ne "3.11") {
            throw "The repo virtual environment is not using Python 3.11. Run .\setup_windows.ps1 to rebuild it."
        }
        return
    }

    $baseSpec = Get-Python311Spec
    $rebuildVenv = $false
    if (Test-Path $VenvPython) {
        $venvSpec = New-PythonSpec $VenvPython
        if ((Get-PythonVersion $venvSpec) -ne "3.11") {
            Write-Step "Rebuilding .venv with Python 3.11"
            Remove-Item -LiteralPath $VenvDir -Recurse -Force
            $rebuildVenv = $true
        }
    } else {
        $rebuildVenv = $true
    }

    if ($rebuildVenv) {
        Write-Step "Creating repo virtual environment"
        $baseArgs = @()
        if ($null -ne $baseSpec.Args) {
            $baseArgs = @($baseSpec.Args)
        }
        if ($baseArgs.Count -gt 0) {
            & $baseSpec.Exe @baseArgs -m venv $VenvDir
        } else {
            & $baseSpec.Exe -m venv $VenvDir
        }
    }

    Write-Step "Upgrading pip tooling"
    & $VenvPython -m pip install --upgrade pip setuptools wheel

    Write-Step "Installing dashboard requirements"
    & $VenvPython -m pip install -r $RequirementsPath
}

function Assert-BundledAssets {
    if (-not (Test-Path $MainPath)) {
        throw "Dashboard entry point is missing: '$MainPath'"
    }
    if (-not (Test-Path $CapsuleDll)) {
        throw "Bundled Capsule DLL is missing: '$CapsuleDll'"
    }
    if (-not (Test-Path $CapsuleSdkDir)) {
        throw "Bundled Capsule SDK directory is missing: '$CapsuleSdkDir'"
    }
    if (-not (Test-Path $HostScript)) {
        throw "Instagram host script is missing: '$HostScript'"
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

function Ensure-WebView2Runtime {
    $version = Get-WebView2Version
    if ($version) {
        Write-Step "Detected Microsoft Edge WebView2 Runtime $version"
        return $version
    }

    if ($CheckOnly) {
        throw "Microsoft Edge WebView2 Runtime is missing. Run .\setup_windows.ps1 without -CheckOnly or install it manually."
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Microsoft Edge WebView2 Runtime is missing and winget is not available. Install it manually from https://go.microsoft.com/fwlink/p/?LinkId=2124703 and rerun .\setup_windows.ps1."
    }

    Write-Step "Installing Microsoft Edge WebView2 Runtime with winget"
    & $winget.Path install --id Microsoft.EdgeWebView2Runtime --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Microsoft Edge WebView2 Runtime. Install it manually from https://go.microsoft.com/fwlink/p/?LinkId=2124703 and rerun .\setup_windows.ps1."
    }

    $version = Get-WebView2Version
    if (-not $version) {
        throw "Microsoft Edge WebView2 Runtime was installed but could not be detected afterward. Rerun .\setup_windows.ps1 or install it manually."
    }

    Write-Step "Detected Microsoft Edge WebView2 Runtime $version"
    return $version
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
print('INSTAGRAM_RUNTIME_OK')
'@
    $checkScript = $checkScript.Replace("__REPO_ROOT__", $RepoRoot)

    Write-Step "Verifying Python runtime dependencies"
    & $VenvPython -c $checkScript
    if ($LASTEXITCODE -ne 0) {
        throw "The repo virtual environment is missing required Instagram dependencies. Rerun .\setup_windows.ps1."
    }
}

try {
    Push-Location $RepoRoot
    Assert-SupportedBranch
    Assert-BundledAssets
    Ensure-Venv
    Ensure-WebView2Runtime | Out-Null
    Assert-PythonRuntime
    Write-Output "SETUP_WINDOWS_OK"
} finally {
    Pop-Location
}

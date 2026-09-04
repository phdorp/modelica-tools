#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Install dependencies for native Windows containers (requires Windows host / Windows Docker engine).
# Mirrors .devcontainer/install_dependencies.sh (Linux) after installation:
#   - Python 3.11, pip, pipx
#   - OpenModelica (omc + omlibrary / Modelica Standard Library)
#   - git, ca-certificates/curl equivalents via Windows native stack
# uv is installed via postCreateCommand (pipx install uv) to keep parity with Linux.
# NOTE: This script only runs on native Windows containers (Dockerfile.windows-native).
# The default Windows devcontainer (Dockerfile) is Linux-based for cross-platform builds (WSL2) and uses install_dependencies.sh.

Write-Host "Installing Windows devcontainer dependencies..."

# ---------------------------------------------------------------------------
# 1. Chocolatey (package manager) - needed for Python / Git if not present
# ---------------------------------------------------------------------------
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:PATH = "$env:PATH;$env:ALLUSERSPROFILE\chocolatey\bin"
    # Refresh session PATH for choco
    Import-Module "$env:ChocolateyInstall\helpers\chocolateyProfile.psm1" -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# 2. Python 3.11 + Git + pipx prerequisites
# ---------------------------------------------------------------------------
Write-Host "Installing Python 3.11, Git and PowerShell via Chocolatey..."
# Use --no-progress to reduce log noise; -y confirms
choco install -y --no-progress python --version 3.11.9
choco install -y --no-progress git
# PowerShell 7 (pwsh) enables && chaining and modern syntax; optional but preferred
try { choco install -y --no-progress powershell } catch { Write-Host "PowerShell 7 install failed (optional): $_" }

# Ensure Python and Scripts are on PATH for this session
$pythonPaths = @(
    "$env:ProgramData\chocolatey\bin",
    "$env:ProgramFiles\Python311\Scripts",
    "$env:ProgramFiles\Python311",
    "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
    "$env:LOCALAPPDATA\Programs\Python\Python311"
)
foreach ($p in $pythonPaths) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}
# Machine-level PATH update for future sessions
$machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
foreach ($p in $pythonPaths) {
    if ((Test-Path $p) -and ($machinePath -notlike "*$p*")) {
        $machinePath = "$p;$machinePath"
    }
}
[Environment]::SetEnvironmentVariable("PATH", $machinePath, "Machine")

# Upgrade pip and install pipx (equivalent to apt install pipx on Linux)
Write-Host "Upgrading pip and installing pipx..."
python -m pip install --upgrade pip
python -m pip install --upgrade pipx
python -m pipx ensurepath

# Ensure pipx bin is on PATH
$pipxBin = "$env:USERPROFILE\.local\bin"
if ((Test-Path $pipxBin) -and ($env:PATH -notlike "*$pipxBin*")) {
    $env:PATH = "$pipxBin;$env:PATH"
}

# ---------------------------------------------------------------------------
# 3. OpenModelica (omc + omlibrary)
#    Mirrors: apt-get install omc omlibrary
#    Strategy: try winget first (if available), then download official installer.
# ---------------------------------------------------------------------------
function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$omcAvailable = Test-CommandAvailable "omc"
if ($omcAvailable) {
    Write-Host "OpenModelica (omc) already available: $(omc --version 2>&1 | Out-String)"
} else {
    $installedViaWinget = $false
    if (Test-CommandAvailable "winget") {
        Write-Host "Attempting OpenModelica install via winget..."
        try {
            winget install --id OpenModelica.OpenModelica -e --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0) {
                # Verify omc actually appeared (winget returns 0 even when package not found in some versions)
                Start-Sleep -Seconds 2
                if (Test-CommandAvailable "omc" -or (Get-ChildItem -Path "C:\Program Files" -Filter "omc.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)) {
                    $installedViaWinget = $true
                    Write-Host "OpenModelica installed via winget."
                } else {
                    Write-Host "winget exit 0 but omc not found, falling back to direct download."
                }
            } else {
                Write-Host "winget install failed with exit code $LASTEXITCODE, falling back to direct download."
            }
        } catch {
            Write-Host "winget install failed, falling back to direct download: $_"
        }
    }

    if (-not $installedViaWinget) {
        Write-Host "Downloading OpenModelica installer..."

        # Pin a known stable release; update when bumping the Linux 'stable' apt suite.
        # Keep this in sync with the version available from https://build.openmodelica.org/apt
        $OMVersion = "1.26.2"

        $urls = @(
            "https://github.com/OpenModelica/OpenModelica/releases/download/v$OMVersion/OpenModelica-v$OMVersion-64bit.exe",
            "https://build.openmodelica.org/omc/builds/windows/releases/$OMVersion/64bit/OpenModelicaSetup-$OMVersion-64bit.exe"
        )

        $tempDir = "C:\TEMP"
        if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory -Path $tempDir | Out-Null }
        $installer = Join-Path $tempDir "OpenModelicaSetup.exe"

        $downloaded = $false
        foreach ($url in $urls) {
            try {
                Write-Host "Trying $url"
                Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
                if ((Test-Path $installer) -and ((Get-Item $installer).Length -gt 1MB)) {
                    $downloaded = $true
                    Write-Host "Downloaded OpenModelica installer from $url"
                    break
                }
            } catch {
                Write-Host "Failed to download from $url : $_"
            }
        }

        if (-not $downloaded) {
            throw "Failed to download OpenModelica installer from all known URLs. Please update OMVersion in install_dependencies.ps1 or install manually from https://openmodelica.org/download/download-windows"
        }

        Write-Host "Running OpenModelica installer silently..."
        # Inno Setup installers support /VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART
        # NSIS installers support /S . Try both flag sets.
        $proc = Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-", "/NORESTART" -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            Write-Host "Exit code $($proc.ExitCode) with /VERYSILENT, retrying with /S"
            $proc = Start-Process -FilePath $installer -ArgumentList "/S" -Wait -PassThru
            if ($proc.ExitCode -ne 0) {
                throw "OpenModelica installer failed with exit code $($proc.ExitCode)"
            }
        }

        Remove-Item -Force $installer -ErrorAction SilentlyContinue
        Write-Host "OpenModelica installer finished."
    }

    # Ensure omc is on PATH for this and future sessions
    $candidateBins = @(
        "C:\Program Files\OpenModelica\bin",
        "C:\Program Files\OpenModelica*",
        "C:\Program Files (x86)\OpenModelica\bin",
        "$env:ProgramFiles\OpenModelica\bin"
    )
    # Discover actual bin via filesystem search if not in standard location
    $discovered = Get-ChildItem -Path "C:\Program Files" -Filter "omc.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($discovered) {
        $omBin = $discovered.Directory.FullName
        if ($env:PATH -notlike "*$omBin*") { $env:PATH = "$omBin;$env:PATH" }
        $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        if ($machinePath -notlike "*$omBin*") {
            [Environment]::SetEnvironmentVariable("PATH", "$omBin;$machinePath", "Machine")
        }
        Write-Host "Added $omBin to PATH"
        # Persist for GitHub Actions (survives step boundary)
        if ($env:GITHUB_PATH) {
            Add-Content -Path $env:GITHUB_PATH -Value $omBin
            Write-Host "Added $omBin to GITHUB_PATH"
        }
        # Derive OPENMODELICAHOME (parent of bin)
        $omHome = Split-Path $omBin -Parent
        if (Test-Path "$omHome\bin\omc.exe") {
            $env:OPENMODELICAHOME = $omHome
            [Environment]::SetEnvironmentVariable("OPENMODELICAHOME", $omHome, "Machine")
            if ($env:GITHUB_ENV) {
                Add-Content -Path $env:GITHUB_ENV -Value "OPENMODELICAHOME=$omHome"
                Add-Content -Path $env:GITHUB_ENV -Value "PATH=$omBin;$env:PATH"
            }
            Write-Host "Set OPENMODELICAHOME=$omHome"
        }
    } else {
        Write-Host "WARNING: omc.exe not found after install - verification will fail. Check installer logs at C:\ProgramData\chocolatey\logs or TEMP."
    }
}

# ---------------------------------------------------------------------------
# 4. Verification - mirrors Linux post-install expectations
# ---------------------------------------------------------------------------
Write-Host "Verifying installations..."
try { Write-Host "python: $(python --version 2>&1)" } catch { Write-Host "python not found" }
try { Write-Host "pip: $(pip --version 2>&1)" } catch { Write-Host "pip not found" }
try { Write-Host "pipx: $(pipx --version 2>&1)" } catch { Write-Host "pipx not found" }
try { Write-Host "git: $(git --version 2>&1)" } catch { Write-Host "git not found" }
try {
    # omc may need full path if PATH not yet refreshed
    $omcCmd = Get-Command omc -ErrorAction SilentlyContinue
    if ($omcCmd) {
        Write-Host "omc: $(omc --version 2>&1 | Out-String)"
    } else {
        $omcExe = Get-ChildItem -Path "C:\Program Files" -Filter "omc.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($omcExe) {
            $ver = & $omcExe.FullName --version 2>&1 | Out-String
            Write-Host "omc found at $($omcExe.FullName): $ver"
        } else { Write-Host "omc not found on PATH (may require container restart)" }
    }
} catch { Write-Host "omc check failed: $_" }

Write-Host "Windows dependencies installation complete. Mirrors Linux container: Python 3.11, pipx, OpenModelica (omc+omlibrary)."

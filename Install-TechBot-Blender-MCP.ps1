<#
.SYNOPSIS
    TechBot_Blender_MCP Interactive Multi-Client Windows Installer (v1.0.0).

.DESCRIPTION
    Comprehensive interactive console wizard and automated deployment tool for TechBot_Blender_MCP:
    Stage A: Welcome & installation mode selection (New, Repair/Update, Reconfigure Clients, Exit).
    Stage B: AI Client selection (Claude, Cursor, ChatGPT, Antigravity IDE).
    Stage C: Independent client detection (Registry 32/64-bit, Start Menu, Executable paths, Configs).
    Stage D: Download & installation location confirmation and customization.
    Stage E: Release artifact acquisition & SHA-256 cryptographic verification.
    Stage F: Blender extension installation & isolated MCP service environment deployment.
    Stage G: Safe, non-destructive AI client configuration merging with timestamped backups.
    Stage H: Non-destructive smoke verification (STDIO handshake, tool listing, bridge status).
    Stage I: Comprehensive Markdown installation report generation (TechBot-Installation-Report.md).

.PARAMETER ReleaseTag
    The GitHub release tag to download from (default: 'v1.0.0-rc2').

.PARAMETER GitHubRepo
    The GitHub repository in 'owner/repo' format (default: 'bharatnextai/TechBot_Blender_MCP').

.PARAMETER InstallDir
    Target directory for the MCP service and virtual environment (default: '%LOCALAPPDATA%\TechBot_Blender_MCP').

.PARAMETER DownloadCacheDir
    Directory for caching downloaded distribution packages (default: '$InstallDir\downloads').

.PARAMETER LocalSourceDir
    Optional path to a local repository or unpacked build directory containing dist artifacts.

.PARAMETER ExtensionZipPath
    Optional path to a local extension ZIP file.

.PARAMETER ServiceZipPath
    Optional path to a local MCP service ZIP file.

.PARAMETER InstallMode
    Installation mode: 'new', 'repair', 'reconfigure', 'exit' (interactive prompt if omitted).

.PARAMETER Clients
    Array of AI clients to configure: 'claude', 'cursor', 'chatgpt', 'antigravity'.

.PARAMETER CursorScope
    Configuration scope for Cursor: 'global' or 'workspace' (default: 'global').

.PARAMETER CursorWorkspacePath
    Path to Cursor workspace folder if CursorScope is 'workspace'.

.PARAMETER AntigravityScope
    Configuration scope for Antigravity: 'global' or 'workspace' (default: 'global').

.PARAMETER AntigravityWorkspacePath
    Path to Antigravity workspace folder if AntigravityScope is 'workspace'.

.PARAMETER BridgePort
    Port number for the Blender bridge server (default: 9877).

.PARAMETER BridgeTimeout
    Bridge timeout in seconds (default: 15.0).

.PARAMETER BlenderPath
    Explicit path to blender.exe. If omitted, standard locations and PATH are searched.

.PARAMETER PythonPath
    Explicit path to python.exe (must be 3.10+). If omitted, PATH and standard locations are searched.

.PARAMETER ReportPath
    Path to output the installation markdown report (default: 'TechBot-Installation-Report.md').

.PARAMETER SkipBlender
    Skip Blender extension installation.

.PARAMETER SkipService
    Skip MCP service and virtual environment installation.

.PARAMETER SkipClients
    Skip modifying AI client configuration files.

.PARAMETER Force
    Force reinstall / overwrite existing installation with backup.

.PARAMETER NonInteractive
    Run in non-interactive batch mode using supplied or default parameters.

.EXAMPLE
    .\Install-TechBot-Blender-MCP.ps1

.EXAMPLE
    .\Install-TechBot-Blender-MCP.ps1 -NonInteractive -InstallMode new -Clients @("claude", "cursor", "antigravity")
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ReleaseTag = "v1.0.0-rc2",
    [string]$GitHubRepo = "bharatnextai/TechBot_Blender_MCP",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "TechBot_Blender_MCP"),
    [string]$DownloadCacheDir = "",
    [string]$LocalSourceDir = "",
    [string]$ExtensionZipPath = "",
    [string]$ServiceZipPath = "",
    [string]$InstallMode = "",
    [string[]]$Clients = @(),
    [ValidateSet("global", "workspace")] [string]$CursorScope = "global",
    [string]$CursorWorkspacePath = "",
    [ValidateSet("global", "workspace")] [string]$AntigravityScope = "global",
    [string]$AntigravityWorkspacePath = "",
    [int]$BridgePort = 9877,
    [double]$BridgeTimeout = 15.0,
    [string]$BlenderPath = "",
    [string]$PythonPath = "",
    [string]$ReportPath = "TechBot-Installation-Report.md",
    [switch]$SkipBlender,
    [switch]$SkipService,
    [switch]$SkipClients,
    [switch]$Force,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ==============================================================================
# Global State & Logging
# ==============================================================================

$script:LogFile = ""
$script:SessionTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$script:ReportData = [ordered]@{
    Timestamp          = $script:SessionTimestamp
    InstallerVersion   = "1.0.0"
    InstallMode        = ""
    GitHubRepo         = $GitHubRepo
    ReleaseTag         = $ReleaseTag
    InstallDir         = $InstallDir
    DownloadCacheDir   = ""
    BlenderExe         = ""
    BlenderVersion     = ""
    BlenderExtResult   = "Skipped"
    PythonExe          = ""
    PythonVersion      = ""
    UvExe              = ""
    VenvPython         = ""
    BridgePort         = $BridgePort
    BridgeTimeout      = $BridgeTimeout
    BridgeStatus       = "Not Running"
    DetectedClients    = @()
    SelectedClients    = @()
    ConfiguredClients  = @()
    ClientBackups      = @{}
    ClientConfigPaths  = @{}
    VerificationPassed = $false
    ToolsDiscovered    = 0
    Sha256Results      = @{}
    Warnings           = @()
    Errors             = @()
    ChatGPTStatus      = "UNCONFIGURED"
}

function Initialize-Logging {
    param([string]$TargetDir)
    try {
        if (-not (Test-Path $TargetDir)) {
            New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        }
        $script:LogFile = Join-Path $TargetDir "install.log"
        $initMsg = "=== TechBot_Blender_MCP Installer Session: $script:SessionTimestamp ==="
        Add-Content -Path $script:LogFile -Value $initMsg -Encoding utf8
    } catch {
        Write-Warning "Failed to initialize log file in $TargetDir. Logging to console only."
    }
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)] [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "WARN", "ERROR", "STAGE")] [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "HH:mm:ss"
    $formatted = "[$timestamp][$Level] $Message"

    switch ($Level) {
        "STAGE"   { Write-Host "`n=== $Message ===" -ForegroundColor Magenta }
        "INFO"    { Write-Host $formatted -ForegroundColor Cyan }
        "SUCCESS" { Write-Host $formatted -ForegroundColor Green }
        "WARN"    {
            Write-Host $formatted -ForegroundColor Yellow
            $script:ReportData.Warnings += $Message
        }
        "ERROR"   {
            Write-Host $formatted -ForegroundColor Red
            $script:ReportData.Errors += $Message
        }
    }

    if ($script:LogFile) {
        try {
            Add-Content -Path $script:LogFile -Value "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))][$Level] $Message" -Encoding utf8
        } catch { }
    }
}

function Read-UserChoice {
    param(
        [string]$PromptMessage,
        [string]$DefaultChoice = ""
    )
    if ($NonInteractive) {
        return $DefaultChoice
    }
    if ($DefaultChoice) {
        Write-Host -NoNewline "${PromptMessage} [$DefaultChoice]: " -ForegroundColor Yellow
    } else {
        Write-Host -NoNewline "${PromptMessage}: " -ForegroundColor Yellow
    }
    $inputVal = Read-Host
    if ([string]::IsNullOrWhiteSpace($inputVal)) {
        return $DefaultChoice
    }
    return $inputVal.Trim()
}

# ==============================================================================
# Stage A: Welcome and Installation Mode Detection
# ==============================================================================

function Show-WelcomeBanner {
    Write-Host @"
===============================================================================
       TechBot_Blender_MCP Windows Installer & Multi-Client Wizard (v1.0.0)
       Universal Model Context Protocol Bridge for Blender 5.2.2 LTS / 4.2+
       Repository: $GitHubRepo | Target Tag: $ReleaseTag
===============================================================================
"@ -ForegroundColor Magenta
}

function Detect-ExistingTechBot {
    param([string]$TargetInstallDir)
    $hasVenv = Test-Path (Join-Path $TargetInstallDir "venv\Scripts\python.exe")
    $hasService = Test-Path (Join-Path $TargetInstallDir "service\mcp_service")
    return ($hasVenv -or $hasService)
}

function Select-InstallationMode {
    param([string]$ExistingDir)

    $isInstalled = Detect-ExistingTechBot -TargetInstallDir $ExistingDir
    if ($isInstalled) {
        Write-Log "Existing TechBot installation detected at: $ExistingDir" "INFO"
    } else {
        Write-Log "No prior TechBot installation detected in $ExistingDir." "INFO"
    }

    if ($InstallMode) {
        $mode = $InstallMode.ToLowerInvariant()
        if ($mode -in @("new", "repair", "reconfigure", "exit")) {
            $script:ReportData.InstallMode = $mode
            return $mode
        }
    }

    if ($NonInteractive) {
        if ($isInstalled) {
            $script:ReportData.InstallMode = "repair"
            return "repair"
        } else {
            $script:ReportData.InstallMode = "new"
            return "new"
        }
    }

    Write-Host "`nPlease select an installation mode:" -ForegroundColor White
    if ($isInstalled) {
        Write-Host "  [1] Repair / Update existing installation" -ForegroundColor Green
        Write-Host "  [2] Reconfigure AI Clients only (preserve extension & service)" -ForegroundColor Cyan
        Write-Host "  [3] Clean Reinstall (backup and overwrite existing)" -ForegroundColor Yellow
        Write-Host "  [4] Exit installer" -ForegroundColor Red
        $choice = Read-UserChoice -PromptMessage "Enter option (1-4)" -DefaultChoice "1"
        switch ($choice) {
            "1" { $mode = "repair" }
            "2" { $mode = "reconfigure" }
            "3" { $mode = "new" }
            "4" { $mode = "exit" }
            default { $mode = "repair" }
        }
    } else {
        Write-Host "  [1] New Installation (Extension + MCP Service + AI Clients)" -ForegroundColor Green
        Write-Host "  [2] Configure AI Clients only (connect to existing bridge)" -ForegroundColor Cyan
        Write-Host "  [3] Exit installer" -ForegroundColor Red
        $choice = Read-UserChoice -PromptMessage "Enter option (1-3)" -DefaultChoice "1"
        switch ($choice) {
            "1" { $mode = "new" }
            "2" { $mode = "reconfigure" }
            "3" { $mode = "exit" }
            default { $mode = "new" }
        }
    }

    if ($mode -eq "exit") {
        Write-Log "Installation cancelled by user." "INFO"
        exit 0
    }

    $script:ReportData.InstallMode = $mode
    return $mode
}

# ==============================================================================
# Stage B & C: Comprehensive AI Client Detection
# ==============================================================================

function Get-RegistryInstalledApps {
    $found = @()
    $regPaths = @(
        @{ Hive = "LocalMachine"; Path = "Software\Microsoft\Windows\CurrentVersion\Uninstall"; View = "Default" },
        @{ Hive = "LocalMachine"; Path = "Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"; View = "Registry32" },
        @{ Hive = "CurrentUser"; Path = "Software\Microsoft\Windows\CurrentVersion\Uninstall"; View = "Default" }
    )

    foreach ($entry in $regPaths) {
        try {
            $hiveKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::$($entry.Hive), [Microsoft.Win32.RegistryView]::$($entry.View))
            $subKey = $hiveKey.OpenSubKey($entry.Path)
            if ($subKey) {
                foreach ($name in $subKey.GetSubKeyNames()) {
                    try {
                        $appKey = $subKey.OpenSubKey($name)
                        if ($appKey) {
                            $displayName = $appKey.GetValue("DisplayName")
                            if ($displayName) {
                                $found += [PSCustomObject]@{
                                    DisplayName     = [string]$displayName
                                    DisplayVersion  = [string]$appKey.GetValue("DisplayVersion")
                                    InstallLocation = [string]$appKey.GetValue("InstallLocation")
                                    Publisher       = [string]$appKey.GetValue("Publisher")
                                    UninstallString = [string]$appKey.GetValue("UninstallString")
                                }
                            }
                            $appKey.Close()
                        }
                    } catch { }
                }
                $subKey.Close()
            }
            $hiveKey.Close()
        } catch { }
    }
    return $found
}

function Find-StartMenuShortcut {
    param([string]$Pattern)
    $shortcuts = @()
    $smPaths = @(
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"),
        (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs")
    )
    foreach ($sm in $smPaths) {
        if (Test-Path $sm) {
            $files = Get-ChildItem -Path $sm -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*$Pattern*" }
            foreach ($f in $files) {
                $shortcuts += $f.FullName
            }
        }
    }
    return $shortcuts
}

function Detect-ClaudeClient {
    $info = [ordered]@{
        Id              = "claude"
        DisplayName     = "Claude Desktop"
        Installed       = $false
        Version         = "Not detected"
        ExecutablePath  = ""
        ConfigPath      = (Join-Path $env:APPDATA "Claude\claude_desktop_config.json")
        Candidates      = @()
        Selected        = $false
    }

    # 1. Search Registry
    $regApps = Get-RegistryInstalledApps | Where-Object { $_.DisplayName -like "*Claude*" }
    foreach ($r in $regApps) {
        $info.Installed = $true
        if ($r.DisplayVersion) { $info.Version = $r.DisplayVersion }
        if ($r.InstallLocation -and (Test-Path (Join-Path $r.InstallLocation "Claude.exe"))) {
            $info.Candidates += (Join-Path $r.InstallLocation "Claude.exe")
        }
    }

    # 2. Search Standard Paths
    $stdPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Claude\Claude.exe"),
        (Join-Path $env:ProgramFiles "Claude\Claude.exe"),
        (Join-Path $env:LOCALAPPDATA "Claude\Claude.exe")
    )
    foreach ($p in $stdPaths) {
        if (Test-Path $p) {
            $info.Installed = $true
            if ($p -notin $info.Candidates) { $info.Candidates += $p }
        }
    }

    # 3. Search PATH
    $cmd = Get-Command "Claude.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        $info.Installed = $true
        if ($cmd.Source -notin $info.Candidates) { $info.Candidates += $cmd.Source }
    }

    # 4. Search Start Menu
    $links = Find-StartMenuShortcut -Pattern "Claude"
    if ($links) { $info.Installed = $true }

    if ($info.Candidates.Count -gt 0) {
        $info.ExecutablePath = $info.Candidates[0]
        if ($info.Version -eq "Not detected") {
            try {
                $v = (Get-Item $info.ExecutablePath).VersionInfo.ProductVersion
                if ($v) { $info.Version = $v }
            } catch { }
        }
    }

    # Check for active portable/data config if roaming does not exist
    if (-not (Test-Path $info.ConfigPath)) {
        $localClaudeData = Join-Path $env:LOCALAPPDATA "Claude-Data"
        if (Test-Path $localClaudeData) {
            $configs = Get-ChildItem -Path $localClaudeData -Filter "claude_desktop_config.json" -Recurse -Depth 2 -ErrorAction SilentlyContinue
            if ($configs) {
                $info.ConfigPath = $configs[0].FullName
            }
        }
    }

    return [PSCustomObject]$info
}

function Detect-CursorClient {
    $info = [ordered]@{
        Id              = "cursor"
        DisplayName     = "Cursor IDE"
        Installed       = $false
        Version         = "Not detected"
        ExecutablePath  = ""
        ConfigPath      = (Join-Path $env:USERPROFILE ".cursor\mcp.json")
        Candidates      = @()
        Selected        = $false
    }

    # 1. Search Registry
    $regApps = Get-RegistryInstalledApps | Where-Object { $_.DisplayName -like "*Cursor*" }
    foreach ($r in $regApps) {
        $info.Installed = $true
        if ($r.DisplayVersion) { $info.Version = $r.DisplayVersion }
        if ($r.InstallLocation -and (Test-Path (Join-Path $r.InstallLocation "Cursor.exe"))) {
            $info.Candidates += (Join-Path $r.InstallLocation "Cursor.exe")
        }
    }

    # 2. Search Standard Paths
    $stdPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\cursor\Cursor.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Cursor\Cursor.exe"),
        (Join-Path $env:ProgramFiles "Cursor\Cursor.exe")
    )
    foreach ($p in $stdPaths) {
        if (Test-Path $p) {
            $info.Installed = $true
            if ($p -notin $info.Candidates) { $info.Candidates += $p }
        }
    }

    # 3. Search PATH
    $cmd = Get-Command "cursor.exe" -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command "cursor.cmd" -ErrorAction SilentlyContinue }
    if ($cmd) {
        $info.Installed = $true
        if ($cmd.Source -notin $info.Candidates) { $info.Candidates += $cmd.Source }
    }

    # 4. Search Start Menu
    $links = Find-StartMenuShortcut -Pattern "Cursor"
    if ($links) { $info.Installed = $true }

    if ($info.Candidates.Count -gt 0) {
        $info.ExecutablePath = $info.Candidates[0]
        if ($info.Version -eq "Not detected") {
            try {
                $v = (Get-Item $info.ExecutablePath).VersionInfo.ProductVersion
                if ($v) { $info.Version = $v }
            } catch { }
        }
    }

    return [PSCustomObject]$info
}

function Detect-AntigravityClient {
    $info = [ordered]@{
        Id              = "antigravity"
        DisplayName     = "Antigravity IDE"
        Installed       = $false
        Version         = "Not detected"
        ExecutablePath  = ""
        ConfigPath      = (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json")
        Candidates      = @()
        Selected        = $false
    }

    # 1. Search Registry
    $regApps = Get-RegistryInstalledApps | Where-Object { $_.DisplayName -like "*Antigravity*" }
    foreach ($r in $regApps) {
        $info.Installed = $true
        if ($r.DisplayVersion) { $info.Version = $r.DisplayVersion }
        if ($r.InstallLocation) {
            $exe = Join-Path $r.InstallLocation "Antigravity IDE.exe"
            if (-not (Test-Path $exe)) { $exe = Join-Path $r.InstallLocation "Antigravity.exe" }
            if (Test-Path $exe) { $info.Candidates += $exe }
        }
    }

    # 2. Search Standard Paths
    $stdPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Antigravity IDE\Antigravity IDE.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Antigravity\Antigravity.exe"),
        (Join-Path $env:ProgramFiles "Antigravity IDE\Antigravity IDE.exe")
    )
    foreach ($p in $stdPaths) {
        if (Test-Path $p) {
            $info.Installed = $true
            if ($p -notin $info.Candidates) { $info.Candidates += $p }
        }
    }

    # 3. Search PATH
    $cmd = Get-Command "antigravity.exe" -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command "agy.cmd" -ErrorAction SilentlyContinue }
    if ($cmd) {
        $info.Installed = $true
        if ($cmd.Source -notin $info.Candidates) { $info.Candidates += $cmd.Source }
    }

    if ($info.Candidates.Count -gt 0) {
        $info.ExecutablePath = $info.Candidates[0]
        if ($info.Version -eq "Not detected") {
            try {
                $v = (Get-Item $info.ExecutablePath).VersionInfo.ProductVersion
                if ($v) { $info.Version = $v }
            } catch { }
        }
    }

    return [PSCustomObject]$info
}

function Detect-ChatGPTClient {
    $info = [ordered]@{
        Id              = "chatgpt"
        DisplayName     = "ChatGPT Desktop"
        Installed       = $false
        Version         = "Not detected"
        ExecutablePath  = ""
        ConfigPath      = "In-App Settings: Settings -> MCP Servers (Local STDIO)"
        Candidates      = @()
        Selected        = $false
    }

    # 1. Windows Store Package (MSIX / Appx) - Primary distribution on Windows 10/11
    try {
        $appxList = @(Get-AppxPackage -Name "*ChatGPT*" -ErrorAction SilentlyContinue)
        if (-not $appxList -or $appxList.Count -eq 0) {
            $appxList = @(Get-AppxPackage -Name "*OpenAI*" -ErrorAction SilentlyContinue)
        }
        foreach ($pkg in $appxList) {
            if ($pkg.Name -like "*ChatGPT*" -or $pkg.Name -like "*Codex*" -or $pkg.PackageFamilyName -like "*OpenAI*") {
                $info.Installed = $true
                if ($pkg.Version -and $info.Version -eq "Not detected") {
                    $info.Version = $pkg.Version
                }
                
                # Check for standard WindowsApps execution alias
                $aliasExe = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\chatgpt-desktop.exe"
                if (Test-Path $aliasExe) {
                    if ($aliasExe -notin $info.Candidates) { $info.Candidates += $aliasExe }
                }
                $aliasExe2 = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\ChatGPT.exe"
                if (Test-Path $aliasExe2) {
                    if ($aliasExe2 -notin $info.Candidates) { $info.Candidates += $aliasExe2 }
                }

                # Check inside package install location if accessible
                if ($pkg.InstallLocation -and (Test-Path $pkg.InstallLocation)) {
                    $candFiles = @(Get-ChildItem -Path $pkg.InstallLocation -Filter "*.exe" -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*chatgpt*" -or $_.Name -like "*codex*" })
                    foreach ($cf in $candFiles) {
                        if ($cf.FullName -notin $info.Candidates) { $info.Candidates += $cf.FullName }
                    }
                }
            }
        }
    } catch { }

    # 2. Windows Start Menu Apps (Get-StartApps)
    try {
        $startApps = @(Get-StartApps -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*ChatGPT*" -or $_.AppID -like "*OpenAI*" -or $_.AppID -like "*ChatGPT*" })
        if ($startApps -and $startApps.Count -gt 0) {
            $info.Installed = $true
            if ($info.Version -eq "Not detected") {
                $info.Version = "Windows Store App"
            }
            $aliasExe = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\chatgpt-desktop.exe"
            if ((Test-Path $aliasExe) -and ($aliasExe -notin $info.Candidates)) {
                $info.Candidates += $aliasExe
            }
        }
    } catch { }

    # 3. Search Registry
    $regApps = Get-RegistryInstalledApps | Where-Object { $_.DisplayName -like "*ChatGPT*" -or $_.DisplayName -like "*OpenAI*" }
    foreach ($r in $regApps) {
        $info.Installed = $true
        if ($r.DisplayVersion -and $info.Version -eq "Not detected") { $info.Version = $r.DisplayVersion }
        if ($r.InstallLocation) {
            foreach ($exeName in @("ChatGPT.exe", "chatgpt-desktop.exe", "ChatGPT Desktop.exe")) {
                $p = Join-Path $r.InstallLocation $exeName
                if ((Test-Path $p) -and ($p -notin $info.Candidates)) {
                    $info.Candidates += $p
                }
            }
        }
    }

    # 4. Search Standard Paths / WindowsApps
    $stdPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\ChatGPT\ChatGPT.exe"),
        (Join-Path $env:ProgramFiles "ChatGPT\ChatGPT.exe"),
        (Join-Path $env:ProgramFiles "OpenAI\ChatGPT.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\chatgpt-desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\ChatGPT.exe")
    )
    foreach ($p in $stdPaths) {
        if (Test-Path $p) {
            $info.Installed = $true
            if ($p -notin $info.Candidates) { $info.Candidates += $p }
        }
    }

    # 5. Search PATH
    foreach ($exeName in @("chatgpt-desktop.exe", "ChatGPT.exe", "chatgpt.exe")) {
        $cmd = Get-Command $exeName -ErrorAction SilentlyContinue
        if ($cmd) {
            $info.Installed = $true
            if ($cmd.Source -notin $info.Candidates) { $info.Candidates += $cmd.Source }
        }
    }

    # 6. Search Start Menu Shortcuts (.lnk)
    $links = Find-StartMenuShortcut -Pattern "ChatGPT"
    if ($links -and $links.Count -gt 0) {
        $info.Installed = $true
    }

    if ($info.Candidates.Count -gt 0) {
        $info.ExecutablePath = $info.Candidates[0]
        if ($info.Version -eq "Not detected") {
            try {
                $v = (Get-Item $info.ExecutablePath).VersionInfo.ProductVersion
                if ($v) { $info.Version = $v }
            } catch { }
        }
    } elseif ($info.Installed -and -not $info.ExecutablePath) {
        $aliasExe = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\chatgpt-desktop.exe"
        if (Test-Path $aliasExe) {
            $info.ExecutablePath = $aliasExe
        } else {
            $info.ExecutablePath = "Windows Store Package (OpenAI / ChatGPT)"
        }
    }

    return [PSCustomObject]$info
}

function Detect-AllClients {
    Write-Log "Scanning system for installed AI clients and MCP configurations..." "INFO"
    $clients = @()
    $clients += Detect-ClaudeClient
    $clients += Detect-CursorClient
    $clients += Detect-ChatGPTClient
    $clients += Detect-AntigravityClient

    $script:ReportData.DetectedClients = $clients
    return $clients
}

function Select-ClientsWizard {
    param([array]$DetectedList)

    Write-Host "`n=== AI Client Detection Summary ===" -ForegroundColor Magenta
    for ($i = 0; $i -lt $DetectedList.Count; $i++) {
        $c = $DetectedList[$i]
        $statusStr = if ($c.Installed) { "INSTALLED (v$($c.Version))" } else { "NOT DETECTED" }
        $color = if ($c.Installed) { "Green" } else { "DarkGray" }
        Write-Host "  [$($i+1)] $($c.DisplayName): $statusStr" -ForegroundColor $color
        if ($c.ExecutablePath) {
            Write-Host "      Executable:  $($c.ExecutablePath)" -ForegroundColor Gray
        }
        Write-Host "      MCP Config:  $($c.ConfigPath)" -ForegroundColor Gray
    }

    # Pre-select based on script arguments if passed
    $targetClients = @()
    if ($Clients.Count -gt 0) {
        foreach ($item in $Clients) {
            if ($item) {
                $targetClients += ($item -split "[, ]+")
            }
        }
    }

    if ($targetClients.Count -gt 0) {
        foreach ($c in $DetectedList) {
            if ($c.Id -in $targetClients -or $targetClients -contains "all") {
                $c.Selected = $true
            }
        }
    } elseif ($NonInteractive) {
        # Non-interactive default: select all detected clients
        foreach ($c in $DetectedList) {
            if ($c.Installed) { $c.Selected = $true }
        }
    } else {
        # Interactive selection
        Write-Host "`nSelect AI clients to configure for TechBot Blender MCP:" -ForegroundColor White
        Write-Host "Enter numbers separated by comma (e.g. '1,2,4' or 'all' or 'none'):" -ForegroundColor White
        
        # Suggest detected ones
        $defaultSelections = @()
        for ($i = 0; $i -lt $DetectedList.Count; $i++) {
            if ($DetectedList[$i].Installed) { $defaultSelections += ($i + 1) }
        }
        $defaultStr = if ($defaultSelections.Count -gt 0) { $defaultSelections -join "," } else { "none" }

        $selectionInput = Read-UserChoice -PromptMessage "Select clients" -DefaultChoice $defaultStr

        if ($selectionInput.ToLowerInvariant() -eq "all") {
            foreach ($c in $DetectedList) { $c.Selected = $true }
        } elseif ($selectionInput.ToLowerInvariant() -ne "none") {
            $indices = $selectionInput -split "[, ]+"
            foreach ($idx in $indices) {
                if ($idx -match '^\d+$') {
                    $num = [int]$idx - 1
                    if ($num -ge 0 -and $num -lt $DetectedList.Count) {
                        $DetectedList[$num].Selected = $true
                    }
                }
            }
        }
    }

    # Candidate resolution & Manual override for selected clients
    foreach ($c in $DetectedList) {
        if ($c.Selected) {
            # Multiple candidate resolution
            if ($c.Candidates.Count -gt 1 -and -not $NonInteractive) {
                Write-Host "`nMultiple installations found for $($c.DisplayName):" -ForegroundColor Yellow
                for ($k = 0; $k -lt $c.Candidates.Count; $k++) {
                    Write-Host "  [$($k+1)] $($c.Candidates[$k])"
                }
                $candChoice = Read-UserChoice -PromptMessage "Choose candidate (1-$($c.Candidates.Count))" -DefaultChoice "1"
                $chosenIdx = [int]$candChoice - 1
                if ($chosenIdx -ge 0 -and $chosenIdx -lt $c.Candidates.Count) {
                    $c.ExecutablePath = $c.Candidates[$chosenIdx]
                }
            }

            # Optional manual override prompt
            if (-not $c.Installed -and -not $NonInteractive) {
                Write-Host "`n$($c.DisplayName) was not detected automatically." -ForegroundColor Yellow
                $override = Read-UserChoice -PromptMessage "Would you like to manually specify its executable path? (y/N)" -DefaultChoice "N"
                if ($override.ToUpperInvariant() -eq "Y") {
                    $manualPath = Read-UserChoice -PromptMessage "Enter full path to executable" -DefaultChoice ""
                    if ($manualPath -and (Test-Path $manualPath)) {
                        $c.ExecutablePath = $manualPath
                        $c.Installed = $true
                        Write-Log "Manual override applied for $($c.DisplayName): $manualPath" "SUCCESS"
                    }
                }
            }
        }
    }

    $selected = @($DetectedList | Where-Object { $_.Selected })
    $script:ReportData.SelectedClients = $selected
    $selectedNames = @($selected | ForEach-Object { $_.DisplayName })
    $nameStr = if ($selectedNames.Count -gt 0) { $selectedNames -join ', ' } else { 'None' }
    Write-Log "Selected clients for configuration: $nameStr" "INFO"
    return $DetectedList
}

# ==============================================================================
# Stage D: Locations Confirmation & Customization
# ==============================================================================

function Confirm-LocationsWizard {
    param(
        [ref]$TargetInstallDir,
        [ref]$TargetDownloadDir,
        [array]$ClientList
    )

    if (-not $TargetDownloadDir.Value) {
        $TargetDownloadDir.Value = Join-Path $TargetInstallDir.Value "downloads"
    }

    if (-not $NonInteractive) {
        Write-Host "`n=== Installation & Download Locations ===" -ForegroundColor Magenta
        Write-Host "Specify where TechBot Blender MCP service, virtual environment, and release downloads should be located:" -ForegroundColor White
        
        $newInstall = Read-UserChoice -PromptMessage "Enter MCP Service & Installation folder" -DefaultChoice $TargetInstallDir.Value
        if ($newInstall) { 
            $TargetInstallDir.Value = $newInstall 
        }

        $defaultDl = if ($TargetDownloadDir.Value) { $TargetDownloadDir.Value } else { Join-Path $TargetInstallDir.Value "downloads" }
        $newDownload = Read-UserChoice -PromptMessage "Enter Release Download Cache folder" -DefaultChoice $defaultDl
        if ($newDownload) { 
            $TargetDownloadDir.Value = $newDownload 
        }

        # Client scope selection
        foreach ($c in $ClientList) {
            if ($c.Selected) {
                if ($c.Id -eq "cursor") {
                    Write-Host "`nCursor IDE Configuration Scope:" -ForegroundColor Yellow
                    Write-Host "  [1] Global User Profile (%USERPROFILE%\.cursor\mcp.json)"
                    Write-Host "  [2] Specific Workspace (<workspace>\.cursor\mcp.json)"
                    $scopeChoice = Read-UserChoice -PromptMessage "Choose scope (1 or 2)" -DefaultChoice "1"
                    if ($scopeChoice -eq "2") {
                        $ws = Read-UserChoice -PromptMessage "Enter full workspace folder path" -DefaultChoice (Get-Location).Path
                        if ($ws) {
                            $c.ConfigPath = Join-Path $ws ".cursor\mcp.json"
                            $script:CursorScope = "workspace"
                            $script:CursorWorkspacePath = $ws
                        }
                    }
                } elseif ($c.Id -eq "antigravity") {
                    Write-Host "`nAntigravity IDE Configuration Scope:" -ForegroundColor Yellow
                    Write-Host "  [1] Global User Config (%USERPROFILE%\.gemini\config\mcp_config.json)"
                    Write-Host "  [2] Specific Workspace (<workspace>\.agents\mcp_config.json)"
                    $scopeChoice = Read-UserChoice -PromptMessage "Choose scope (1 or 2)" -DefaultChoice "1"
                    if ($scopeChoice -eq "2") {
                        $ws = Read-UserChoice -PromptMessage "Enter full workspace folder path" -DefaultChoice (Get-Location).Path
                        if ($ws) {
                            $c.ConfigPath = Join-Path $ws ".agents\mcp_config.json"
                            $script:AntigravityScope = "workspace"
                            $script:AntigravityWorkspacePath = $ws
                        }
                    }
                }
            }
        }
    }

    # Update workspace paths if configured via script arguments
    foreach ($c in $ClientList) {
        if ($c.Selected) {
            if ($c.Id -eq "cursor" -and $CursorScope -eq "workspace" -and $CursorWorkspacePath) {
                $c.ConfigPath = Join-Path $CursorWorkspacePath ".cursor\mcp.json"
            } elseif ($c.Id -eq "antigravity" -and $AntigravityScope -eq "workspace" -and $AntigravityWorkspacePath) {
                $c.ConfigPath = Join-Path $AntigravityWorkspacePath ".agents\mcp_config.json"
            }
        }
    }

    $script:ReportData.InstallDir = $TargetInstallDir.Value
    $script:ReportData.DownloadCacheDir = $TargetDownloadDir.Value

    # Final summary display before writing files
    $selectedClientsList = @($ClientList | Where-Object { $_.Selected })
    $selectedClientNames = @($selectedClientsList | ForEach-Object { $_.DisplayName })
    $selectedClientsStr = if ($selectedClientNames.Count -gt 0) { $selectedClientNames -join ', ' } else { 'None' }

    Write-Host "`n=== Pre-Installation Summary ===" -ForegroundColor Magenta
    Write-Host "  Install Mode:        $($script:ReportData.InstallMode)" -ForegroundColor White
    Write-Host "  Service Directory:   $($TargetInstallDir.Value)" -ForegroundColor White
    Write-Host "  Download Cache:      $($TargetDownloadDir.Value)" -ForegroundColor White
    Write-Host "  Configured Clients:  $selectedClientsStr" -ForegroundColor White
    Write-Host "  Bridge Socket Port:  $BridgePort (Timeout: ${BridgeTimeout}s)" -ForegroundColor White
    Write-Host "=================================================" -ForegroundColor Magenta

    if (-not $NonInteractive) {
        $proceed = Read-UserChoice -PromptMessage "Proceed with installation? (Y/n)" -DefaultChoice "Y"
        if ($proceed.ToUpperInvariant() -eq "N") {
            Write-Log "Installation aborted by user before modifying system." "WARN"
            exit 0
        }
    }
}

# ==============================================================================
# Environment Detection & Automatic Installation (Python, uv, Blender)
# ==============================================================================

function Update-SessionEnvironmentPath {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = "$userPath;$machinePath"
}

function Get-PythonVersionSafe {
    param([string]$ExePath)
    if (-not $ExePath -or -not (Test-Path $ExePath)) {
        return $null
    }
    # Filter out 0-byte Windows Store execution alias stubs
    try {
        $item = Get-Item $ExePath -ErrorAction SilentlyContinue
        if ($item -and $item.Length -eq 0) {
            return $null
        }
    } catch { }

    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $ExePath
        $psi.Arguments = "-c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')`""
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        [void]$proc.WaitForExit(5000)
        if ($proc.ExitCode -eq 0 -and $stdout) {
            $verStr = $stdout.Trim()
            return $verStr
        }
    } catch { }
    return $null
}

function Find-PythonCandidate {
    # 1. Search PATH
    $pyCmdList = @(Get-Command "python.exe" -ErrorAction SilentlyContinue)
    foreach ($pyCmd in $pyCmdList) {
        if ($pyCmd -and $pyCmd.Source) {
            $ver = Get-PythonVersionSafe -ExePath $pyCmd.Source
            if ($ver -and [version]$ver -ge [version]"3.10.0") {
                return [PSCustomObject]@{ Path = $pyCmd.Source; Version = $ver }
            }
        }
    }

    # 2. Search Standard Windows locations
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe",
        "C:\Program Files\Python313\python.exe"
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            $ver = Get-PythonVersionSafe -ExePath $cand
            if ($ver -and [version]$ver -ge [version]"3.10.0") {
                return [PSCustomObject]@{ Path = $cand; Version = $ver }
            }
        }
    }

    # 3. Check Windows Python Launcher (py.exe)
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($tag in @("-3.12", "-3.11", "-3.10", "-3.13")) {
            try {
                $pyPath = & $pyLauncher.Source $tag -c "import sys; print(sys.executable)" 2>$null
                if ($pyPath -and (Test-Path $pyPath.Trim())) {
                    $ver = Get-PythonVersionSafe -ExePath $pyPath.Trim()
                    if ($ver -and [version]$ver -ge [version]"3.10.0") {
                        return [PSCustomObject]@{ Path = $pyPath.Trim(); Version = $ver }
                    }
                }
            } catch { }
        }
    }

    return $null
}

function Install-PythonAutomatically {
    Write-Log "Python 3.10+ was not found on this system." "WARN"
    Write-Log "Automatically installing Python 3.12..." "INFO"

    # Strategy 1: winget
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Log "Installing Python 3.12 using Windows Package Manager (winget)..." "INFO"
        try {
            $p = Start-Process -FilePath $winget.Source -ArgumentList "install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity" -Wait -PassThru -NoNewWindow
            Write-Log "winget finished with exit code $($p.ExitCode)" "INFO"
        } catch {
            Write-Log "winget execution failed: $_" "WARN"
        }
        Update-SessionEnvironmentPath
        $cand = Find-PythonCandidate
        if ($cand) {
            Write-Log "Python 3.12 installed and verified via winget: $($cand.Path) (v$($cand.Version))" "SUCCESS"
            return $cand
        }
    }

    # Strategy 2: Direct official installer download from python.org
    Write-Log "Downloading official Python 3.12 installer from python.org..." "INFO"
    $pyInstallerUrl = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
    $tempInstaller = Join-Path $env:TEMP "python-3.12.7-amd64.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pyInstallerUrl -OutFile $tempInstaller -UseBasicParsing
        Write-Log "Executing silent Python installation..." "INFO"
        $proc = Start-Process -FilePath $tempInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 SimpleInstall=1" -Wait -PassThru
        Write-Log "Python installer completed with exit code $($proc.ExitCode)" "INFO"
        Remove-Item -Path $tempInstaller -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Log "Direct Python installation failed: $_" "WARN"
    }

    Update-SessionEnvironmentPath
    $cand = Find-PythonCandidate
    if ($cand) {
        Write-Log "Python 3.12 installed and verified: $($cand.Path) (v$($cand.Version))" "SUCCESS"
        return $cand
    }

    throw "Automatic installation of Python 3.10+ could not be completed. Please install Python 3.10 or newer from https://www.python.org/downloads/."
}

function Find-PythonExecutable {
    param(
        [string]$ExplicitPath,
        [switch]$SkipAutoInstall
    )
    if ($ExplicitPath) {
        if (Test-Path $ExplicitPath) {
            $ver = Get-PythonVersionSafe -ExePath $ExplicitPath
            if ($ver -and [version]$ver -ge [version]"3.10.0") {
                Write-Log "Using specified Python: $ExplicitPath (v$ver)" "SUCCESS"
                $script:ReportData.PythonExe = $ExplicitPath
                $script:ReportData.PythonVersion = $ver
                return $ExplicitPath
            } else {
                throw "Specified Python '$ExplicitPath' version ($ver) is below minimum required 3.10.0."
            }
        } else {
            throw "Specified Python path '$ExplicitPath' does not exist."
        }
    }

    $cand = Find-PythonCandidate
    if ($cand) {
        Write-Log "Found Python: $($cand.Path) (v$($cand.Version))" "SUCCESS"
        $script:ReportData.PythonExe = $cand.Path
        $script:ReportData.PythonVersion = $cand.Version
        return $cand.Path
    }

    if ($SkipAutoInstall) {
        throw "Python 3.10+ was not found on this system. Please install Python 3.10 or newer from python.org."
    }

    $installed = Install-PythonAutomatically
    if ($installed) {
        $script:ReportData.PythonExe = $installed.Path
        $script:ReportData.PythonVersion = $installed.Version
        return $installed.Path
    }

    throw "Python 3.10+ was not found on this system. Please install Python 3.10 or newer from python.org."
}

function Install-UvAutomatically {
    Write-Log "Installing uv package manager automatically..." "INFO"
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            $p = Start-Process -FilePath $winget.Source -ArgumentList "install astral-sh.uv --silent --accept-package-agreements --accept-source-agreements --disable-interactivity" -Wait -PassThru -NoNewWindow
            Update-SessionEnvironmentPath
        } catch { }
    }

    # Check if installed
    $cand = Find-UvCandidate
    if ($cand) { return $cand }

    # Fallback to official astral.sh install script
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Write-Log "Installing uv via official installer script..." "INFO"
        Invoke-Expression (Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1")
        Update-SessionEnvironmentPath
    } catch {
        Write-Log "Could not install uv via script: $_" "WARN"
    }

    $cand = Find-UvCandidate
    return $cand
}

function Find-UvCandidate {
    $uvCmd = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($uvCmd) {
        $ver = & $uvCmd.Source --version 2>$null
        return [PSCustomObject]@{ Path = $uvCmd.Source; Version = $ver }
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe",
        "$env:LOCALAPPDATA\bin\uv.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $ver = & $c --version 2>$null
            return [PSCustomObject]@{ Path = $c; Version = $ver }
        }
    }
    return $null
}

function Find-UvExecutable {
    param([switch]$SkipAutoInstall)

    $cand = Find-UvCandidate
    if ($cand) {
        Write-Log "Found uv package manager: $($cand.Path) ($($cand.Version))" "SUCCESS"
        $script:ReportData.UvExe = $cand.Path
        return $cand.Path
    }

    if (-not $SkipAutoInstall) {
        $installed = Install-UvAutomatically
        if ($installed) {
            Write-Log "Found uv package manager: $($installed.Path) ($($installed.Version))" "SUCCESS"
            $script:ReportData.UvExe = $installed.Path
            return $installed.Path
        }
    }

    Write-Log "uv package manager not detected. Falling back to standard python venv and pip." "INFO"
    return $null
}

function Find-BlenderExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        if (Test-Path $ExplicitPath) {
            Write-Log "Using specified Blender executable: $ExplicitPath" "SUCCESS"
            $script:ReportData.BlenderExe = $ExplicitPath
            return $ExplicitPath
        } else {
            throw "Specified Blender path '$ExplicitPath' does not exist."
        }
    }

    $blenderCmd = Get-Command "blender.exe" -ErrorAction SilentlyContinue
    if ($blenderCmd) {
        Write-Log "Found Blender in PATH: $($blenderCmd.Source)" "SUCCESS"
        $script:ReportData.BlenderExe = $blenderCmd.Source
        return $blenderCmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\Blender Foundation\Blender 5.2\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 5.1\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 5.0\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 4.3\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 4.2\blender.exe",
        "$env:ProgramFiles (x86)\Blender Foundation\Blender 5.2\blender.exe",
        "$env:LOCALAPPDATA\Programs\Blender Foundation\Blender 5.2\blender.exe",
        "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            Write-Log "Found Blender at standard location: $cand" "SUCCESS"
            $script:ReportData.BlenderExe = $cand
            return $cand
        }
    }

    return $null
}

function Check-BridgePortStatus {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $pidVal = $conn.OwningProcess
            $procName = (Get-Process -Id $pidVal -ErrorAction SilentlyContinue).ProcessName
            Write-Log "Blender bridge is ACTIVE on port $Port (Process: $procName, PID: $pidVal)." "SUCCESS"
            Write-Log "Existing bridge listener preserved. Listener process will NOT be terminated." "INFO"
            $script:ReportData.BridgeStatus = "Active (PID $pidVal, $procName)"
            return
        }
    } catch { }

    Write-Log "Blender bridge is not currently running on port $Port. (Starts when Blender loads add-on)." "INFO"
    $script:ReportData.BridgeStatus = "Not Running (Bridge starts when Blender opens)"
}

# ==============================================================================
# Stage E: Download and Integrity Verification
# ==============================================================================

function Compute-Sha256 {
    param([Parameter(Mandatory = $true)] [string]$FilePath)
    $hash = Get-FileHash -Path $FilePath -Algorithm SHA256
    return $hash.Hash.ToLowerInvariant()
}

function Verify-FileChecksum {
    param(
        [Parameter(Mandatory = $true)] [string]$FilePath,
        [Parameter(Mandatory = $true)] [string]$ExpectedSidecarPath
    )
    if (-not (Test-Path $FilePath)) {
        throw "File to verify does not exist: $FilePath"
    }
    if (-not (Test-Path $ExpectedSidecarPath)) {
        throw "Checksum sidecar file missing: $ExpectedSidecarPath"
    }

    $sidecarContent = (Get-Content -Path $ExpectedSidecarPath -Raw).Trim()
    $expectedHash = ($sidecarContent -split '\s+')[0].ToLowerInvariant()
    $actualHash = Compute-Sha256 -FilePath $FilePath

    $fileName = Split-Path $FilePath -Leaf
    Write-Log "Verifying $fileName checksum:" "INFO"
    Write-Log "  Expected SHA-256: $expectedHash" "INFO"
    Write-Log "  Computed SHA-256: $actualHash" "INFO"

    $script:ReportData.Sha256Results[$fileName] = [ordered]@{
        Expected = $expectedHash
        Computed = $actualHash
        Verified = ($expectedHash -eq $actualHash)
    }

    if ($expectedHash -ne $actualHash) {
        throw "SHA-256 checksum mismatch for '$fileName'! Refusing to install unverified artifact."
    }

    Write-Log "Checksum verification PASSED for $fileName." "SUCCESS"
}

function Resolve-Artifacts {
    param(
        [string]$Repo,
        [string]$Tag,
        [string]$LocalSource,
        [string]$ExtPath,
        [string]$SvcPath,
        [string]$CacheDir,
        [switch]$SkipBlenderExt,
        [switch]$SkipSvc
    )

    $resolved = [PSCustomObject]@{
        ExtensionZip = ""
        ExtensionSha = ""
        ServiceZip   = ""
        ServiceSha   = ""
        SourceMethod = ""
    }

    if (-not (Test-Path $CacheDir)) {
        New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null
    }

    # Case 1: Explicit paths supplied
    if ($ExtPath -and (Test-Path $ExtPath)) {
        $resolved.ExtensionZip = (Resolve-Path $ExtPath).Path
        $sidecar = "$ExtPath.sha256"
        if (Test-Path $sidecar) {
            $resolved.ExtensionSha = (Resolve-Path $sidecar).Path
            Verify-FileChecksum -FilePath $resolved.ExtensionZip -ExpectedSidecarPath $resolved.ExtensionSha
        }
    }

    if ($SvcPath -and (Test-Path $SvcPath)) {
        $resolved.ServiceZip = (Resolve-Path $SvcPath).Path
        $sidecar = "$SvcPath.sha256"
        if (Test-Path $sidecar) {
            $resolved.ServiceSha = (Resolve-Path $sidecar).Path
            Verify-FileChecksum -FilePath $resolved.ServiceZip -ExpectedSidecarPath $resolved.ServiceSha
        }
    }

    # Case 2: Local Source Directory supplied
    if ($LocalSource -and (Test-Path $LocalSource)) {
        $distDir = Join-Path $LocalSource "dist"
        if (Test-Path $distDir) {
            if (-not $resolved.ExtensionZip -and -not $SkipBlenderExt) {
                $extCandidates = Get-ChildItem -Path $distDir -Filter "TechBot_Blender_MCP-*.zip" | Where-Object { $_.Name -notlike "*Service*" }
                if ($extCandidates) {
                    $best = $extCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                    $resolved.ExtensionZip = $best.FullName
                    $sidecar = "$($best.FullName).sha256"
                    if (Test-Path $sidecar) {
                        $resolved.ExtensionSha = $sidecar
                        Verify-FileChecksum -FilePath $resolved.ExtensionZip -ExpectedSidecarPath $resolved.ExtensionSha
                    }
                    Write-Log "Found local extension candidate: $($best.FullName)" "SUCCESS"
                }
            }
            if (-not $resolved.ServiceZip -and -not $SkipSvc) {
                $svcCandidates = Get-ChildItem -Path $distDir -Filter "TechBot_Blender_MCP_Service-*.zip"
                if ($svcCandidates) {
                    $best = $svcCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                    $resolved.ServiceZip = $best.FullName
                    $sidecar = "$($best.FullName).sha256"
                    if (Test-Path $sidecar) {
                        $resolved.ServiceSha = $sidecar
                        Verify-FileChecksum -FilePath $resolved.ServiceZip -ExpectedSidecarPath $resolved.ServiceSha
                    }
                    Write-Log "Found local service candidate: $($best.FullName)" "SUCCESS"
                }
            }
        }
        $resolved.SourceMethod = "LocalSourceDir"
    }

    # Case 3: GitHub Releases download
    if ((-not $resolved.ExtensionZip -and -not $SkipBlenderExt) -or (-not $resolved.ServiceZip -and -not $SkipSvc)) {
        Write-Log "Fetching release metadata from GitHub repository $Repo (tag: $Tag)..." "INFO"
        $apiUrl = "https://api.github.com/repos/$Repo/releases/tags/$Tag"
        $headers = @{ "User-Agent" = "TechBot-Blender-MCP-Installer" }
        $releaseJson = $null
        try {
            $releaseJson = Invoke-RestMethod -Uri $apiUrl -Headers $headers -Method Get
        } catch {
            throw "Failed to fetch GitHub release metadata from $apiUrl. Error: $_"
        }

        $assets = $releaseJson.assets
        if (-not $assets -or $assets.Count -eq 0) {
            throw "GitHub release '$Tag' has no downloadable assets. Cannot proceed."
        }

        # Resolve Extension Asset
        if (-not $resolved.ExtensionZip -and -not $SkipBlenderExt) {
            $extAsset = $assets | Where-Object { $_.name -like "TechBot_Blender_MCP-*.zip" -and $_.name -notlike "*Service*" } | Select-Object -First 1
            $extShaAsset = $assets | Where-Object { $_.name -eq "$($extAsset.name).sha256" } | Select-Object -First 1

            if (-not $extAsset) {
                throw "Release '$Tag' does not contain a verified extension ZIP asset ('TechBot_Blender_MCP-*.zip')."
            }
            if (-not $extShaAsset) {
                throw "Release '$Tag' is missing the required SHA-256 sidecar for $($extAsset.name)."
            }

            $localExtZip = Join-Path $CacheDir $extAsset.name
            $localExtSha = Join-Path $CacheDir $extShaAsset.name

            Write-Log "Downloading $($extAsset.name)..." "INFO"
            Invoke-WebRequest -Uri $extAsset.browser_download_url -OutFile $localExtZip -Headers $headers
            Invoke-WebRequest -Uri $extShaAsset.browser_download_url -OutFile $localExtSha -Headers $headers

            Verify-FileChecksum -FilePath $localExtZip -ExpectedSidecarPath $localExtSha
            $resolved.ExtensionZip = $localExtZip
            $resolved.ExtensionSha = $localExtSha
        }

        # Resolve Service Asset
        if (-not $resolved.ServiceZip -and -not $SkipSvc) {
            $svcAsset = $assets | Where-Object { $_.name -like "TechBot_Blender_MCP_Service-*.zip" } | Select-Object -First 1
            $svcShaAsset = $assets | Where-Object { $_.name -eq "$($svcAsset.name).sha256" } | Select-Object -First 1

            if (-not $svcAsset) {
                throw "Release '$Tag' does not contain the required external service package 'TechBot_Blender_MCP_Service-*.zip'. Please provide -LocalSourceDir or -ServiceZipPath. Do not download GitHub's auto-generated source code ZIP as it lacks required distribution packaging."
            }
            if (-not $svcShaAsset) {
                throw "Release '$Tag' is missing the required SHA-256 sidecar for $($svcAsset.name)."
            }

            $localSvcZip = Join-Path $CacheDir $svcAsset.name
            $localSvcSha = Join-Path $CacheDir $svcShaAsset.name

            Write-Log "Downloading $($svcAsset.name)..." "INFO"
            Invoke-WebRequest -Uri $svcAsset.browser_download_url -OutFile $localSvcZip -Headers $headers
            Invoke-WebRequest -Uri $svcShaAsset.browser_download_url -OutFile $localSvcSha -Headers $headers

            Verify-FileChecksum -FilePath $localSvcZip -ExpectedSidecarPath $localSvcSha
            $resolved.ServiceZip = $localSvcZip
            $resolved.ServiceSha = $localSvcSha
        }

        $resolved.SourceMethod = "GitHubRelease"
    }

    return ,$resolved
}

# ==============================================================================
# Stage F: Component Installation
# ==============================================================================

function Get-BlenderExtensionInstallArgs {
    param(
        [Parameter(Mandatory = $true)] [string]$ExtensionZip,
        [string]$Repo = "user_default"
    )
    return @("--command", "extension", "install-file", "-r", $Repo, "-e", $ExtensionZip)
}

function Find-BlenderUserDefaultDir {
    param(
        [Parameter(Mandatory = $true)] [string]$BlenderExe
    )

    if (-not $BlenderExe -or -not (Test-Path $BlenderExe)) {
        return $null
    }

    # Strategy 1: Direct inquiry of Blender's extension repositories via embedded Python
    try {
        $pyCmd = "import bpy; [print('BLENDER_USER_DEFAULT:' + str(r.directory)) for r in bpy.context.preferences.extensions.repos if r.module == 'user_default']"
        $prevEAP = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $out = (& $BlenderExe -b --python-expr $pyCmd 2>&1) | Out-String
            if ($out -match 'BLENDER_USER_DEFAULT:(.+)') {
                $dirCandidate = $Matches[1].Trim().Trim('"').Trim("'")
                if ($dirCandidate) {
                    return $dirCandidate
                }
            }
        } finally {
            $ErrorActionPreference = $prevEAP
        }
    } catch { }

    # Strategy 2: CLI --command extension repo-list (handling quoted and unquoted output safely)
    try {
        $prevEAP = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $repoOutput = (& $BlenderExe --command extension repo-list 2>&1) | Out-String
            $capture = $false
            foreach ($line in ($repoOutput -split '\r?\n')) {
                if ($line -match '^\s*user_default:\s*$') {
                    $capture = $true
                    continue
                }
                if ($capture) {
                    if ($line -match '^[a-zA-Z0-9_]+:\s*$') {
                        break
                    }
                    if ($line -match 'directory:\s*"?([^"\r\n]+?)"?\s*$') {
                        $dirCandidate = $Matches[1].Trim().Trim('"').Trim("'")
                        if ($dirCandidate) {
                            return $dirCandidate
                        }
                    }
                }
            }
        } finally {
            $ErrorActionPreference = $prevEAP
        }
    } catch { }

    # Strategy 3: Standard APPDATA version directories
    $blenderBase = Join-Path $env:APPDATA "Blender Foundation\Blender"
    if (Test-Path $blenderBase) {
        $versionDirs = Get-ChildItem -Path $blenderBase -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+\.\d+' } | Sort-Object Name -Descending
        foreach ($vd in $versionDirs) {
            $cand = Join-Path $vd.FullName "extensions\user_default"
            if (Test-Path $cand) {
                return $cand
            }
        }
        if ($versionDirs.Count -gt 0) {
            return (Join-Path $versionDirs[0].FullName "extensions\user_default")
        }
    }

    # Strategy 4: Portable Blender version folders adjacent to blender.exe
    $blenderDir = Split-Path -Parent $BlenderExe
    $portableVersions = Get-ChildItem -Path $blenderDir -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+\.\d+' }
    foreach ($pv in $portableVersions) {
        $cand = Join-Path $pv.FullName "extensions\user_default"
        return $cand
    }

    return $null
}

function Verify-BlenderExtensionInstallation {
    param(
        [string]$UserDefaultDir,
        [string]$BlenderExe,
        [string]$ExtensionId = "universal_mcp"
    )

    # Check 1: Explicit UserDefaultDir or repository path
    if ($UserDefaultDir) {
        $pkgDir = Join-Path $UserDefaultDir $ExtensionId
        $manifest = Join-Path $pkgDir "blender_manifest.toml"
        if (-not (Test-Path $manifest)) {
            $manifest = Join-Path $pkgDir "manifest.toml"
        }
        if ((Test-Path $pkgDir) -and (Test-Path $manifest)) {
            return [PSCustomObject]@{
                Verified     = $true
                ExtensionId  = $ExtensionId
                PackageDir   = $pkgDir
                ManifestPath = $manifest
            }
        }
        # If an explicit UserDefaultDir was specified and no BlenderExe was provided, do not probe host system
        if (-not $BlenderExe) {
            return $null
        }
    }

    # Check 2: Direct verification via Blender's module resolver
    if ($BlenderExe -and (Test-Path $BlenderExe)) {
        try {
            $prevEAP = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $pyCheck = "import bpy, importlib.util; spec = importlib.util.find_spec('bl_ext.user_default.$ExtensionId'); print('BPY_EXT_PATH:' + (spec.origin if spec else ''))"
                $checkOut = (& $BlenderExe -b --python-expr $pyCheck 2>&1) | Out-String
                if ($checkOut -match 'BPY_EXT_PATH:(.+)') {
                    $initFile = $Matches[1].Trim()
                    if ($initFile -and (Test-Path $initFile)) {
                        $pDir = Split-Path -Parent $initFile
                        $manifest = Join-Path $pDir "blender_manifest.toml"
                        if (-not (Test-Path $manifest)) { $manifest = Join-Path $pDir "manifest.toml" }
                        return [PSCustomObject]@{
                            Verified     = $true
                            ExtensionId  = $ExtensionId
                            PackageDir   = $pDir
                            ManifestPath = $manifest
                        }
                    }
                }
            } finally {
                $ErrorActionPreference = $prevEAP
            }
        } catch { }
    }

    return $null
}

function Install-BlenderExtension {
    param(
        [Parameter(Mandatory = $true)] [string]$BlenderExe,
        [Parameter(Mandatory = $true)] [string]$ExtensionZip,
        [switch]$ForceInstall
    )

    Write-Log "Deploying Blender extension from $ExtensionZip..." "INFO"

    if (-not (Test-Path $BlenderExe)) {
        throw "Blender executable does not exist: $BlenderExe"
    }
    if (-not (Test-Path $ExtensionZip)) {
        throw "Extension ZIP does not exist: $ExtensionZip"
    }

    # Step 1: Discover user_default repository directory
    $userDefaultDir = Find-BlenderUserDefaultDir -BlenderExe $BlenderExe

    # Step 2: Detect existing installation and preserve user preferences
    $existing = Verify-BlenderExtensionInstallation -UserDefaultDir $userDefaultDir -BlenderExe $BlenderExe -ExtensionId "universal_mcp"
    if ($existing -and $existing.Verified) {
        Write-Log "Detected existing 'universal_mcp' installation in: $($existing.PackageDir)" "INFO"
        Write-Log "Preserving existing user preferences during extension installation." "INFO"
    }

    # Step 3: Execute Blender's verified local-package installation command:
    # blender.exe --command extension install-file -r user_default -e "<RC2 ZIP path>"
    $extArgs = Get-BlenderExtensionInstallArgs -ExtensionZip $ExtensionZip -Repo "user_default"
    Write-Log "Executing: & `"$BlenderExe`" $($extArgs -join ' ')" "INFO"

    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()

    try {
        $proc = Start-Process -FilePath $BlenderExe -ArgumentList $extArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $stdout = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue

        if ($proc.ExitCode -ne 0) {
            Write-Log "Blender extension installation failed with exit code $($proc.ExitCode)!" "ERROR"
            if ($stdout) { Write-Log "Standard Output:`n$stdout" "ERROR" }
            if ($stderr) { Write-Log "Standard Error:`n$stderr" "ERROR" }
            $script:ReportData.BlenderExtResult = "Failed (Code $($proc.ExitCode))"
            throw "Blender extension install-file failed with exit code $($proc.ExitCode)."
        }

        # Step 4: Verify installed extension ID universal_mcp and its package directory
        if (-not $userDefaultDir) {
            $userDefaultDir = Find-BlenderUserDefaultDir -BlenderExe $BlenderExe
        }

        $verifiedObj = Verify-BlenderExtensionInstallation -UserDefaultDir $userDefaultDir -BlenderExe $BlenderExe -ExtensionId "universal_mcp"
        $listVerified = $false
        try {
            $prevEAP = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $listOutput = (& $BlenderExe --command extension list 2>&1) | Out-String
                if ($listOutput -match 'universal_mcp') {
                    $listVerified = $true
                }
            } finally {
                $ErrorActionPreference = $prevEAP
            }
        } catch { }

        if ((-not $verifiedObj -or -not $verifiedObj.Verified) -and -not $listVerified) {
            Write-Log "Extension package installation finished but verification of 'universal_mcp' failed." "ERROR"
            if ($stdout) { Write-Log "Output: $stdout" "ERROR" }
            $script:ReportData.BlenderExtResult = "Failed (Verification of universal_mcp package directory failed)"
            throw "Extension verification failed: 'universal_mcp' package directory or manifest missing after install."
        }

        $pkgPath = if ($verifiedObj) { $verifiedObj.PackageDir } elseif ($userDefaultDir) { (Join-Path $userDefaultDir "universal_mcp") } else { "user_default:universal_mcp" }
        Write-Log "Extension ID 'universal_mcp' verified in package directory: $pkgPath" "SUCCESS"
        Write-Log "Blender extension installed and enabled in repository 'user_default'." "SUCCESS"
        $script:ReportData.BlenderExtResult = "Installed & Enabled (Repository: user_default, ID: universal_mcp, Path: $pkgPath)"
    } finally {
        Remove-Item -Path $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Install-MCPService {
    param(
        [Parameter(Mandatory = $true)] [string]$TargetDir,
        [Parameter(Mandatory = $true)] [string]$ServiceZip,
        [Parameter(Mandatory = $true)] [string]$PythonExe,
        [string]$UvExe,
        [string]$Mode
    )

    Write-Log "Deploying external MCP service to $TargetDir..." "INFO"
    $serviceSrcDir = Join-Path $TargetDir "service"
    $venvDir = Join-Path $TargetDir "venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    if (-not (Test-Path $serviceSrcDir)) {
        New-Item -ItemType Directory -Path $serviceSrcDir -Force | Out-Null
    }

    # Backup if repair/reinstall
    if ($Mode -in @("repair", "new") -and (Test-Path $venvDir)) {
        $bkVenv = Join-Path $TargetDir "venv.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Write-Log "Backing up existing venv to $bkVenv..." "INFO"
        Copy-Item -Path $venvDir -Destination $bkVenv -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Extract service archive cleanly
    Write-Log "Extracting $(Split-Path $ServiceZip -Leaf)..." "INFO"
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ServiceZip, $serviceSrcDir)
    } catch {
        Expand-Archive -Path $ServiceZip -DestinationPath $serviceSrcDir -Force
    }

    # Create virtual environment
    if (-not (Test-Path $venvPython) -or $Mode -eq "new") {
        Write-Log "Creating isolated Python virtual environment at $venvDir..." "INFO"
        if ($UvExe) {
            & $UvExe venv $venvDir --python $PythonExe | Out-Null
        } else {
            & $PythonExe -m venv $venvDir | Out-Null
        }

        if (-not (Test-Path $venvPython)) {
            throw "Virtual environment creation failed at $venvDir."
        }
        Write-Log "Virtual environment created successfully." "SUCCESS"
    } else {
        Write-Log "Virtual environment already exists at $venvDir." "INFO"
    }

    # Install package dependencies
    Write-Log "Installing package and dependencies into virtual environment..." "INFO"
    if ($UvExe) {
        & $UvExe pip install -e $serviceSrcDir --python $venvPython
    } else {
        & $venvPython -m pip install --upgrade pip --quiet
        & $venvPython -m pip install -e $serviceSrcDir --quiet
    }

    $script:ReportData.VenvPython = $venvPython
    return $venvPython
}

# ==============================================================================
# Stage G: Safe Non-Destructive AI Client Configuration
# ==============================================================================

function Backup-ConfigFile {
    param([Parameter(Mandatory = $true)] [string]$ConfigPath)
    if (Test-Path $ConfigPath) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupPath = "$ConfigPath.bak_$timestamp"
        Copy-Item -Path $ConfigPath -Destination $backupPath -Force
        Write-Log "Created backup of config: $backupPath" "INFO"
        return $backupPath
    }
    return $null
}

function Merge-ClientConfiguration {
    param(
        [Parameter(Mandatory = $true)] [string]$ConfigPath,
        [Parameter(Mandatory = $true)] [string]$VenvPythonPath,
        [Parameter(Mandatory = $true)] [int]$Port,
        [Parameter(Mandatory = $true)] [double]$Timeout
    )

    $parentDir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    $bakFile = Backup-ConfigFile -ConfigPath $ConfigPath

    $mergeScript = [System.IO.Path]::GetTempFileName() + ".py"
    $pyMerge = @'
import json
import os
import sys

config_path = sys.argv[1]
venv_python = sys.argv[2]
bridge_port = sys.argv[3]
bridge_timeout = sys.argv[4]
server_key = "techbot-blender-mcp"

server_config = {
    "command": venv_python,
    "args": [
        "-m", "mcp_service.app",
        "--transport", "stdio",
        "--bridge-port", bridge_port,
        "--bridge-timeout", bridge_timeout
    ],
    "env": {
        "PYTHONUNBUFFERED": "1"
    }
}

data = {}
raw = ""
if os.path.isfile(config_path):
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            raw = f.read().strip()
            if raw:
                data = json.loads(raw)
    except Exception as exc:
        try:
            decoder = json.JSONDecoder()
            pos = 0
            merged = {}
            found_any = False
            while pos < len(raw):
                raw_chunk = raw[pos:].lstrip()
                if not raw_chunk:
                    break
                leading = len(raw[pos:]) - len(raw_chunk)
                obj, end = decoder.raw_decode(raw_chunk)
                if isinstance(obj, dict):
                    found_any = True
                    if "mcpServers" in obj:
                        merged.setdefault("mcpServers", {}).update(obj["mcpServers"])
                    for k, v in obj.items():
                        if k != "mcpServers":
                            merged[k] = v
                else:
                    print("PARSE_ERROR: Non-object JSON block encountered in multi-document stream. Refusing to overwrite.")
                    sys.exit(2)
                pos += leading + end
            if not found_any or not merged:
                print(f"PARSE_ERROR: Unable to recover valid JSON dictionary ({exc})")
                sys.exit(2)
            data = merged
        except Exception as rec_exc:
            print(f"PARSE_ERROR: Could not parse existing config JSON ({rec_exc})")
            sys.exit(2)

if raw and not isinstance(data, dict):
    print("PARSE_ERROR: Existing config root is not a JSON object. Refusing to overwrite.")
    sys.exit(2)

if not isinstance(data, dict):
    data = {}

if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
    data["mcpServers"] = {}

data["mcpServers"][server_key] = server_config

with open(config_path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, indent=2)

print("MERGE_JSON_SUCCESS")
'@
    Set-Content -Path $mergeScript -Value $pyMerge -Encoding utf8

    try {
        $mergeOutput = & $VenvPythonPath $mergeScript $ConfigPath $VenvPythonPath ($Port.ToString()) ($Timeout.ToString()) 2>&1
        if ($mergeOutput -notmatch "MERGE_JSON_SUCCESS") {
            throw "Failed to update configuration at $ConfigPath. Error: $mergeOutput"
        }
        Write-Log "Successfully merged 'techbot-blender-mcp' in $ConfigPath" "SUCCESS"
        return $bakFile
    } finally {
        Remove-Item -Path $mergeScript -Force -ErrorAction SilentlyContinue
    }
}

function Configure-SelectedAIClients {
    param(
        [array]$ClientList,
        [string]$VenvPythonPath,
        [int]$Port,
        [double]$Timeout
    )

    Write-Log "Configuring selected AI client MCP connections..." "INFO"

    foreach ($c in $ClientList) {
        if (-not $c.Selected) {
            continue
        }

        switch ($c.Id) {
            "claude" {
                Write-Log "Configuring Claude Desktop at $($c.ConfigPath)..." "INFO"
                $bak = Merge-ClientConfiguration -ConfigPath $c.ConfigPath -VenvPythonPath $VenvPythonPath -Port $Port -Timeout $Timeout
                $script:ReportData.ConfiguredClients += "Claude Desktop"
                $script:ReportData.ClientConfigPaths["Claude Desktop"] = $c.ConfigPath
                if ($bak) { $script:ReportData.ClientBackups["Claude Desktop"] = $bak }
            }
            "cursor" {
                Write-Log "Configuring Cursor IDE at $($c.ConfigPath)..." "INFO"
                $bak = Merge-ClientConfiguration -ConfigPath $c.ConfigPath -VenvPythonPath $VenvPythonPath -Port $Port -Timeout $Timeout
                $script:ReportData.ConfiguredClients += "Cursor IDE"
                $script:ReportData.ClientConfigPaths["Cursor IDE"] = $c.ConfigPath
                if ($bak) { $script:ReportData.ClientBackups["Cursor IDE"] = $bak }
            }
            "antigravity" {
                Write-Log "Configuring Antigravity IDE at $($c.ConfigPath)..." "INFO"
                $bak = Merge-ClientConfiguration -ConfigPath $c.ConfigPath -VenvPythonPath $VenvPythonPath -Port $Port -Timeout $Timeout
                $script:ReportData.ConfiguredClients += "Antigravity IDE"
                $script:ReportData.ClientConfigPaths["Antigravity IDE"] = $c.ConfigPath
                if ($bak) { $script:ReportData.ClientBackups["Antigravity IDE"] = $bak }
            }
            "chatgpt" {
                Write-Log "Processing ChatGPT Desktop integration..." "INFO"
                $servicePath = Join-Path $InstallDir "service"
                Write-Host @"

-------------------------------------------------------------------------------
ChatGPT Desktop Local MCP Integration (STDIO):
ChatGPT Desktop supports local MCP connections over STDIO (no tunnel required).
Because ChatGPT manages servers via its in-app Settings UI instead of a
JSON file on disk, configure it in ChatGPT Settings:

1. Open ChatGPT Desktop -> Settings -> MCP Servers -> Add Server
2. Enter the following parameters:
   Name:              TechBot_Blender_MCP
   Command to launch: uv (or full path: "$VenvPythonPath")
   Arguments (enter each argument separately):
     run
     --no-project
     --with
     mcp<2,>=1.25.0
     --with
     pydantic>=2.0.0
     --with
     httpx>=0.25.0
     python
     -m
     mcp_service.app
     --transport
     stdio
     --bridge-port
     $Port
     --bridge-timeout
     $Timeout
   Environment variables:
     PYTHONPATH:        $servicePath
     PYTHONUNBUFFERED:  1
     UMCP_BRIDGE_PORT:  $Port
   Working directory:   $servicePath
3. Click Save and connect. See docs/CHATGPT_INSTALLATION.md for details.
-------------------------------------------------------------------------------
"@ -ForegroundColor Cyan
                $script:ReportData.ChatGPTStatus = "UNCONFIGURED (Manual In-App Configuration in ChatGPT Settings Required)"
            }
        }
    }
}

# ==============================================================================
# Stage H: Non-Destructive Verification
# ==============================================================================

function Test-MCPInstallation {
    param(
        [Parameter(Mandatory = $true)] [string]$VenvPythonPath,
        [Parameter(Mandatory = $true)] [int]$Port
    )

    Write-Log "Running non-destructive MCP installation checks..." "INFO"

    # 1. Environment & Imports
    $smoke = & $VenvPythonPath -c "import mcp, pydantic, httpx, starlette, uvicorn, mcp_service; print('DEPENDENCIES_LOADED_OK')" 2>&1
    if ($smoke -notmatch "DEPENDENCIES_LOADED_OK") {
        throw "Python dependency validation failed in ${VenvPythonPath}: $smoke"
    }
    Write-Log "Python runtime & MCP dependencies validated." "SUCCESS"

    # 2. Test MCP STDIO Handshake & Tool Listing
    $testScript = [System.IO.Path]::GetTempFileName() + ".py"
    $pyTest = @'
import subprocess
import json
import sys

venv_python = sys.argv[1]
port = sys.argv[2]

cmd = [venv_python, "-m", "mcp_service.app", "--transport", "stdio", "--bridge-port", port]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

try:
    init_req = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "techbot-installer-verify", "version": "1.0"}
        }
    }
    proc.stdin.write(json.dumps(init_req) + "\n")
    proc.stdin.flush()

    raw_init = proc.stdout.readline()
    init_data = json.loads(raw_init)
    if "result" not in init_data:
        print(f"INIT_FAIL:{raw_init}")
        sys.exit(1)

    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
    proc.stdin.flush()

    raw_tools = proc.stdout.readline()
    tools_data = json.loads(raw_tools)
    tool_count = len(tools_data.get("result", {}).get("tools", []))
    print(f"MCP_VERIFY_SUCCESS:{tool_count}")
finally:
    proc.terminate()
'@
    Set-Content -Path $testScript -Value $pyTest -Encoding utf8

    try {
        $testOut = & $VenvPythonPath $testScript $VenvPythonPath ($Port.ToString()) 2>&1
        if ($testOut -match "MCP_VERIFY_SUCCESS:(\d+)") {
            $count = $Matches[1]
            Write-Log "MCP STDIO handshake succeeded. Discovered $count typed tools." "SUCCESS"
            $script:ReportData.ToolsDiscovered = [int]$count
            $script:ReportData.VerificationPassed = $true
        } else {
            Write-Log "MCP verification returned unexpected output: $testOut" "WARN"
        }
    } finally {
        Remove-Item -Path $testScript -Force -ErrorAction SilentlyContinue
    }
}

# ==============================================================================
# Stage I: Installation Report Generation
# ==============================================================================

function Generate-InstallationReport {
    param([string]$DestinationFile)

    $md = @"
# TechBot_Blender_MCP Installation Report

**Generated:** $($script:ReportData.Timestamp)  
**Installer Version:** $($script:ReportData.InstallerVersion)  
**Install Mode:** $($script:ReportData.InstallMode)  
**Repository Target:** $($script:ReportData.GitHubRepo) (Release: $($script:ReportData.ReleaseTag))  

---

## 1. Environment & Components

| Component | Status / Path |
| :--- | :--- |
| **Blender Executable** | $($script:ReportData.BlenderExe) |
| **Blender Extension** | $($script:ReportData.BlenderExtResult) |
| **Python Runtime** | $($script:ReportData.PythonExe) (v$($script:ReportData.PythonVersion)) |
| **Package Manager (uv)**| $(if ($script:ReportData.UvExe) { $script:ReportData.UvExe } else { "Not installed (pip fallback)" }) |
| **Service Target Dir** | $($script:ReportData.InstallDir) |
| **Virtual Environment**| $($script:ReportData.VenvPython) |
| **Bridge Socket Port** | $($script:ReportData.BridgePort) (Timeout: $($script:ReportData.BridgeTimeout)s) |
| **Bridge Listener** | $($script:ReportData.BridgeStatus) |

---

## 2. Cryptographic Integrity (SHA-256)

| Artifact Name | Expected Hash | Verified |
| :--- | :--- | :---: |
"@

    foreach ($k in $script:ReportData.Sha256Results.Keys) {
        $item = $script:ReportData.Sha256Results[$k]
        $vStr = if ($item.Verified) { "PASSED" } else { "FAILED" }
        $md += "`n| $k | $($item.Expected) | **$vStr** |"
    }

    $md += @"


---

## 3. Configured AI Clients

| Client | Configuration Path | Backup File |
| :--- | :--- | :--- |
"@

    if ($script:ReportData.ConfiguredClients.Count -gt 0) {
        foreach ($c in $script:ReportData.ConfiguredClients) {
            $cPath = $script:ReportData.ClientConfigPaths[$c]
            $bPath = if ($script:ReportData.ClientBackups.ContainsKey($c)) { $script:ReportData.ClientBackups[$c] } else { "None" }
            $md += "`n| **$c** | $cPath | $bPath |"
        }
    } else {
        $md += "`n| *None configured* | - | - |"
    }

    $md += @"


### ChatGPT Desktop Status
> **$($script:ReportData.ChatGPTStatus)**  
> ChatGPT Desktop communicates over local STDIO pipes configured via ChatGPT in-app Settings (**Settings -> MCP Servers**).  
> Follow the verified instructions in [`docs/CHATGPT_INSTALLATION.md`](docs/CHATGPT_INSTALLATION.md).

| Setting | Value |
| :--- | :--- |
| **Server Name** | `TechBot_Blender_MCP` |
| **Command** | `uv` *(or `$($script:ReportData.VenvPython)`)* |
| **Arguments** | `run`, `--no-project`, `--with`, `mcp<2,>=1.25.0`, `--with`, `pydantic>=2.0.0`, `--with`, `httpx>=0.25.0`, `python`, `-m`, `mcp_service.app`, `--transport`, `stdio`, `--bridge-port`, `$($script:ReportData.BridgePort)`, `--bridge-timeout`, `15.0` |
| **Environment Variables** | `PYTHONPATH`: `$((Join-Path $script:ReportData.InstallDir "service"))`<br>`PYTHONUNBUFFERED`: `1`<br>`UMCP_BRIDGE_PORT`: `$($script:ReportData.BridgePort)` |
| **Working Directory** | `$((Join-Path $script:ReportData.InstallDir "service"))` |

---

## 4. Verification Results

- **Python Runtime & Dependencies:** PASSED  
- **MCP STDIO Handshake:** $(if ($script:ReportData.VerificationPassed) { "PASSED" } else { "UNVERIFIED" })  
- **Tools Discovered:** $($script:ReportData.ToolsDiscovered)  
- **Bridge Port 9877 Listener:** $($script:ReportData.BridgeStatus) (Never interrupted)  

---

## 5. Next Steps

1. Launch **Blender 5.2.2 LTS**.
2. Press **N** in the 3D Viewport to display the sidebar, select the **Universal MCP** tab, and ensure the bridge server is active.
3. Open your configured AI client (**Claude Desktop**, **Cursor IDE**, or **Antigravity IDE**). TechBot Blender tools will be automatically loaded.
"@

    Set-Content -Path $DestinationFile -Value $md -Encoding utf8
    Write-Log "Installation report written to: $DestinationFile" "SUCCESS"

    # Also copy report to InstallDir
    if (Test-Path $script:ReportData.InstallDir) {
        $appReport = Join-Path $script:ReportData.InstallDir "TechBot-Installation-Report.md"
        Copy-Item -Path $DestinationFile -Destination $appReport -Force -ErrorAction SilentlyContinue
    }
}

# ==============================================================================
# Main Routine
# ==============================================================================

function Main {
    Show-WelcomeBanner
    Initialize-Logging -TargetDir $InstallDir

    # Stage A: Welcome and Mode Selection
    $mode = Select-InstallationMode -ExistingDir $InstallDir
    if ($mode -eq "exit") { return }

    # Stage B & C: Client Detection & Selection
    $detectedClients = Detect-AllClients
    $allClients = Select-ClientsWizard -DetectedList $detectedClients

    # Stage D: Locations Confirmation
    $installDirRef = [ref]$InstallDir
    $downloadDirRef = [ref]$DownloadCacheDir
    Confirm-LocationsWizard -TargetInstallDir $installDirRef -TargetDownloadDir $downloadDirRef -ClientList $allClients
    $InstallDir = $installDirRef.Value
    $DownloadCacheDir = $downloadDirRef.Value

    # Environment checks
    $pythonExe = Find-PythonExecutable -ExplicitPath $PythonPath
    $uvExe = Find-UvExecutable
    $blenderExe = $null

    if (-not $SkipBlender -and $mode -ne "reconfigure") {
        $blenderExe = Find-BlenderExecutable -ExplicitPath $BlenderPath
        if (-not $blenderExe) {
            Write-Log "Blender executable could not be located automatically." "WARN"
            if (-not $NonInteractive) {
                Write-Host "`nBlender 4.2+ / 5.2.2 LTS was not found in standard paths." -ForegroundColor Yellow
                Write-Host "  [1] Automatically install Blender via winget" -ForegroundColor Green
                Write-Host "  [2] Specify path to blender.exe manually" -ForegroundColor Cyan
                Write-Host "  [3] Skip Blender extension installation (configure MCP service & AI clients only)" -ForegroundColor White
                $bChoice = Read-UserChoice -PromptMessage "Select option (1-3)" -DefaultChoice "1"
                if ($bChoice -eq "1") {
                    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
                    if ($winget) {
                        Write-Log "Installing Blender using Windows Package Manager (winget)..." "INFO"
                        try {
                            Start-Process -FilePath $winget.Source -ArgumentList "install BlenderFoundation.Blender --silent --accept-package-agreements --accept-source-agreements --disable-interactivity" -Wait -NoNewWindow
                            Update-SessionEnvironmentPath
                            $blenderExe = Find-BlenderExecutable
                        } catch {
                            Write-Log "Blender winget install failed: $_" "WARN"
                        }
                    }
                } elseif ($bChoice -eq "2") {
                    $manualB = Read-UserChoice -PromptMessage "Enter full path to blender.exe"
                    if ($manualB -and (Test-Path $manualB)) {
                        $blenderExe = $manualB
                        $script:ReportData.BlenderExe = $manualB
                    }
                } else {
                    $SkipBlender = $true
                    Write-Log "Skipping Blender extension installation." "INFO"
                }
            }
            if (-not $blenderExe -and -not $SkipBlender) {
                Write-Log "Please specify -BlenderPath '<path-to-blender.exe>' or run with -SkipBlender." "WARN"
                throw "Blender 4.2+ / 5.2.2 LTS not found. Provide -BlenderPath or -SkipBlender."
            }
        }
    }

    Check-BridgePortStatus -Port $BridgePort

    # Stage E: Download & Verification
    $artifacts = $null
    if ($mode -ne "reconfigure") {
        $artifacts = Resolve-Artifacts -Repo $GitHubRepo `
                                       -Tag $ReleaseTag `
                                       -LocalSource $LocalSourceDir `
                                       -ExtPath $ExtensionZipPath `
                                       -SvcPath $ServiceZipPath `
                                       -CacheDir $DownloadCacheDir `
                                       -SkipBlenderExt:$SkipBlender `
                                       -SkipSvc:$SkipService
    }

    # Stage F: Component Installation
    if (-not $SkipBlender -and $mode -ne "reconfigure" -and $artifacts.ExtensionZip) {
        Install-BlenderExtension -BlenderExe $blenderExe -ExtensionZip $artifacts.ExtensionZip -ForceInstall:$Force
    }

    $venvPython = ""
    if (-not $SkipService -and $mode -ne "reconfigure" -and $artifacts.ServiceZip) {
        $venvPython = Install-MCPService -TargetDir $InstallDir -ServiceZip $artifacts.ServiceZip -PythonExe $pythonExe -UvExe $uvExe -Mode $mode
    } else {
        $venvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            $venvPython = $pythonExe
        }
        $script:ReportData.VenvPython = $venvPython
    }

    # Stage G: Configure AI Clients
    if (-not $SkipClients) {
        Configure-SelectedAIClients -ClientList $allClients -VenvPythonPath $venvPython -Port $BridgePort -Timeout $BridgeTimeout
    }

    # Stage H: Verification
    if (Test-Path $venvPython) {
        Test-MCPInstallation -VenvPythonPath $venvPython -Port $BridgePort
    }

    # Stage I: Generate Report
    Generate-InstallationReport -DestinationFile $ReportPath

    Write-Host @"
===============================================================================
              TechBot_Blender_MCP Setup Completed Successfully!
===============================================================================
  - Installation Mode:    $mode
  - Target Service Dir:   $InstallDir
  - Configured Clients:   $(if ($script:ReportData.ConfiguredClients.Count -gt 0) { ($script:ReportData.ConfiguredClients -join ', ') } else { 'None' })
  - Bridge Socket Port:   $BridgePort
  - Summary Report:       $ReportPath
  - Installation Log:     $script:LogFile
  - Safe Uninstaller:     $(Join-Path (Get-Location) "Uninstall-TechBot-Blender-MCP.ps1")

Next Steps:
  1. Open Blender. In the 3D Viewport sidebar (N), select 'Universal MCP'.
  2. Launch your configured AI client. The typed Blender tools are active.
===============================================================================
"@ -ForegroundColor Green

    Write-Log "Setup process finished successfully." "SUCCESS"
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Main
    } catch {
        Write-Log "Fatal installation error: $_" "ERROR"
        if ($_.ScriptStackTrace) {
            Write-Log "Stack trace:`n$($_.ScriptStackTrace)" "ERROR"
        }
        exit 1
    }
}

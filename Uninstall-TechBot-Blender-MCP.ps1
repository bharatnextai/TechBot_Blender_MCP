<#
.SYNOPSIS
    Production-quality Windows uninstaller for TechBot_Blender_MCP.

.DESCRIPTION
    Safely removes TechBot_Blender_MCP:
    1. Uninstalls the extension package from Blender via native extension operators.
    2. Removes the 'techbot-blender-mcp' server entry from Claude Desktop, Antigravity, and Cursor.
    3. Creates timestamped backups of all client configuration files prior to removal.
    4. Preserves all other configured MCP servers, settings, and unrelated profiles.
    5. Cleans up the application directory and virtual environment in %LOCALAPPDATA%\TechBot_Blender_MCP.

.PARAMETER InstallDir
    Target directory for the MCP service and virtual environment (default: '%LOCALAPPDATA%\TechBot_Blender_MCP').

.PARAMETER Clients
    Array of AI clients to clean: 'claude', 'antigravity', 'cursor' (default: all three).

.PARAMETER WorkspacePaths
    Optional array of workspace directories to clean workspace-level MCP configs (.cursor\mcp.json, .agents\mcp_config.json).

.PARAMETER BlenderPath
    Explicit path to blender.exe. If omitted, standard locations and PATH are searched.

.PARAMETER SkipBlender
    Skip uninstalling the extension from Blender.

.PARAMETER KeepLogs
    Preserve installation and uninstallation logs in the application directory.

.PARAMETER Force
    Force uninstallation without interactive prompts.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "TechBot_Blender_MCP"),
    [string[]]$Clients = @("claude", "antigravity", "cursor", "chatgpt"),
    [string[]]$WorkspacePaths = @(),
    [string]$BlenderPath = "",
    [string]$ChatGPTConfigPath = "",
    [switch]$SkipBlender,
    [switch]$KeepLogs,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ==============================================================================
# Helper Functions: Logging
# ==============================================================================

$script:LogFile = ""
if (Test-Path $InstallDir) {
    $script:LogFile = Join-Path $InstallDir "uninstall.log"
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)] [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "WARN", "ERROR")] [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "HH:mm:ss"
    $formatted = "[$timestamp][$Level] $Message"

    switch ($Level) {
        "INFO"    { Write-Host $formatted -ForegroundColor Cyan }
        "SUCCESS" { Write-Host $formatted -ForegroundColor Green }
        "WARN"    { Write-Host $formatted -ForegroundColor Yellow }
        "ERROR"   { Write-Host $formatted -ForegroundColor Red }
    }

    if ($script:LogFile) {
        try {
            Add-Content -Path $script:LogFile -Value "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))][$Level] $Message" -Encoding utf8
        } catch { }
    }
}

function Write-Banner {
    Write-Host @"
===============================================================================
       TechBot_Blender_MCP Windows Uninstaller
       Target Application Directory: $InstallDir
===============================================================================
"@ -ForegroundColor Magenta
}

# ==============================================================================
# Blender Uninstallation
# ==============================================================================

function Find-BlenderExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return $ExplicitPath
    }
    $blenderCmd = Get-Command "blender.exe" -ErrorAction SilentlyContinue
    if ($blenderCmd) {
        return $blenderCmd.Source
    }
    $candidates = @(
        "$env:ProgramFiles\Blender Foundation\Blender 5.2\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 5.1\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 5.0\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 4.3\blender.exe",
        "$env:ProgramFiles\Blender Foundation\Blender 4.2\blender.exe"
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            return $cand
        }
    }
    return $null
}

function Uninstall-BlenderExtension {
    param([string]$BlenderExe)

    Write-Log "Attempting to uninstall extension 'universal_mcp' from Blender..." "INFO"

    $outTemp = [System.IO.Path]::GetTempFileName()
    $errTemp = [System.IO.Path]::GetTempFileName()

    try {
        $proc = Start-Process -FilePath $BlenderExe -ArgumentList @("--command", "extension", "remove", "universal_mcp") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outTemp -RedirectStandardError $errTemp
        $stdout = Get-Content $outTemp -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $errTemp -Raw -ErrorAction SilentlyContinue

        if ($proc.ExitCode -eq 0 -or $stdout -match 'Removed "universal_mcp"') {
            Write-Log "Blender extension 'universal_mcp' uninstalled successfully." "SUCCESS"
        } else {
            Write-Log "Notice during Blender extension uninstallation: $stdout $stderr" "INFO"
        }
    } catch {
        Write-Log "Notice during Blender extension uninstallation: $_" "WARN"
    } finally {
        Remove-Item -Path $outTemp, $errTemp -Force -ErrorAction SilentlyContinue
    }
}

# ==============================================================================
# Client Configuration Cleanup
# ==============================================================================

function Remove-ClientServerEntry {
    param([string]$ConfigPath)

    if (-not (Test-Path $ConfigPath)) {
        return
    }

    Write-Log "Cleaning MCP configuration from $ConfigPath..." "INFO"

    # Backup before edit
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = "$ConfigPath.bak_uninstall_$timestamp"
    Copy-Item -Path $ConfigPath -Destination $backupPath -Force
    Write-Log "Created backup at $backupPath" "INFO"

    $cleanScript = [System.IO.Path]::GetTempFileName() + ".py"
    $isToml = $ConfigPath.EndsWith(".toml", [System.StringComparison]::OrdinalIgnoreCase)

    if ($isToml) {
        $pyClean = @'
import os
import re
import sys

config_path = sys.argv[1]
server_key = "techbot-blender-mcp"

if not os.path.isfile(config_path):
    print("NO_FILE")
    sys.exit(0)

try:
    with open(config_path, "r", encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
except Exception as exc:
    print(f"PARSE_ERROR:{exc}")
    sys.exit(1)

out = []
skip = False
removed = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("["):
        m = re.match(r"^\[\s*mcp_servers\.[\"']?techbot[-_]blender[-_]mcp[\"']?(\.|\s*\])", stripped)
        if m:
            skip = True
            removed = True
            continue
        else:
            skip = False
    if not skip:
        out.append(line)

cleaned = "\n".join(out).strip() + "\n"
with open(config_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(cleaned)

if removed:
    print(f"REMOVED_KEY:{server_key}")
else:
    print(f"KEY_NOT_FOUND:{server_key}")

print("CLEAN_JSON_SUCCESS")
'@
    } else {
        $pyClean = @'
import json
import os
import sys

config_path = sys.argv[1]
server_key = "techbot-blender-mcp"

if not os.path.isfile(config_path):
    print("NO_FILE")
    sys.exit(0)

try:
    with open(config_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
except Exception:
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
        decoder = json.JSONDecoder()
        pos = 0
        merged = {}
        while pos < len(raw):
            raw_chunk = raw[pos:].lstrip()
            if not raw_chunk:
                break
            leading = len(raw[pos:]) - len(raw_chunk)
            obj, end = decoder.raw_decode(raw_chunk)
            if isinstance(obj, dict):
                if "mcpServers" in obj:
                    merged.setdefault("mcpServers", {}).update(obj["mcpServers"])
                for k, v in obj.items():
                    if k != "mcpServers":
                        merged[k] = v
            pos += leading + end
        data = merged
    except Exception as exc:
        print(f"PARSE_ERROR:{exc}")
        sys.exit(1)

if isinstance(data, dict) and "mcpServers" in data and isinstance(data["mcpServers"], dict):
    if server_key in data["mcpServers"]:
        del data["mcpServers"][server_key]
        print(f"REMOVED_KEY:{server_key}")
    else:
        print(f"KEY_NOT_FOUND:{server_key}")

with open(config_path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, indent=2)

print("CLEAN_JSON_SUCCESS")
'@
    }
    Set-Content -Path $cleanScript -Value $pyClean -Encoding utf8

    try {
        $pyExe = (Get-Command "python.exe" -ErrorAction SilentlyContinue).Source
        if (-not $pyExe) {
            $pyExe = "$InstallDir\venv\Scripts\python.exe"
        }
        if ($pyExe -and (Test-Path $pyExe)) {
            $res = & $pyExe $cleanScript $ConfigPath 2>&1
            Write-Log "Client config cleanup result: $res" "SUCCESS"
        } else {
            Write-Log "Python not available to clean JSON cleanly. Please remove 'techbot-blender-mcp' manually from $ConfigPath" "WARN"
        }
    } finally {
        Remove-Item -Path $cleanScript -Force -ErrorAction SilentlyContinue
    }
}

function Cleanup-AIClients {
    param(
        [string[]]$SelectedClients,
        [string[]]$Workspaces
    )

    $targetPaths = @()

    foreach ($client in $SelectedClients) {
        $lower = $client.ToLowerInvariant()
        switch ($lower) {
            "claude" {
                $targetPaths += (Join-Path $env:APPDATA "Claude\claude_desktop_config.json")
                $claudeData = Join-Path $env:LOCALAPPDATA "Claude-Data"
                if (Test-Path $claudeData) {
                    $configs = Get-ChildItem -Path $claudeData -Filter "claude_desktop_config.json" -Recurse -Depth 2 -ErrorAction SilentlyContinue
                    foreach ($cf in $configs) { $targetPaths += $cf.FullName }
                }
            }
            "antigravity" {
                $targetPaths += (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json")
            }
            "cursor" {
                $targetPaths += (Join-Path $env:USERPROFILE ".cursor\mcp.json")
            }
            "chatgpt" {
                $codexToml = if ($ChatGPTConfigPath) { $ChatGPTConfigPath } else { Join-Path $env:USERPROFILE ".codex\config.toml" }
                if (Test-Path $codexToml) {
                    $targetPaths += $codexToml
                }
            }
        }
    }

    # Workspace specific configurations
    foreach ($ws in $Workspaces) {
        if (Test-Path $ws) {
            $targetPaths += (Join-Path $ws ".cursor\mcp.json")
            $targetPaths += (Join-Path $ws ".agents\mcp_config.json")
        }
    }

    $uniquePaths = $targetPaths | Select-Object -Unique
    foreach ($p in $uniquePaths) {
        if (Test-Path $p) {
            Remove-ClientServerEntry -ConfigPath $p
        }
    }
}

# ==============================================================================
# Main Uninstaller Routine
# ==============================================================================

function Main {
    Write-Banner

    if (-not $Force) {
        Write-Host "This will remove TechBot_Blender_MCP components and MCP configurations." -ForegroundColor Yellow
        Write-Host -NoNewline "Are you sure you want to proceed? (y/N): " -ForegroundColor Yellow
        $resp = Read-Host
        if ($resp.Trim().ToUpperInvariant() -ne "Y") {
            Write-Log "Uninstallation cancelled by user." "INFO"
            return
        }
    }

    # 1. Uninstall Blender extension
    if (-not $SkipBlender) {
        $blenderExe = Find-BlenderExecutable -ExplicitPath $BlenderPath
        if ($blenderExe) {
            Uninstall-BlenderExtension -BlenderExe $blenderExe
        } else {
            Write-Log "Blender executable not found. Skipping Blender extension uninstallation." "WARN"
        }
    }

    # 2. Clean client JSON configurations
    Cleanup-AIClients -SelectedClients $Clients -Workspaces $WorkspacePaths

    # 3. Clean InstallDir
    if (Test-Path $InstallDir) {
        Write-Log "Cleaning application directory: $InstallDir..." "INFO"
        if ($KeepLogs) {
            $subdirs = @("venv", "service", "downloads")
            foreach ($sub in $subdirs) {
                $p = Join-Path $InstallDir $sub
                if (Test-Path $p) {
                    Remove-Item -Path $p -Recurse -Force -ErrorAction SilentlyContinue
                    Write-Log "Removed $p" "INFO"
                }
            }
            Write-Log "Preserved log files in $InstallDir" "INFO"
        } else {
            try {
                Remove-Item -Path $InstallDir -Recurse -Force
                Write-Log "Removed application directory: $InstallDir" "SUCCESS"
            } catch {
                Write-Log "Could not remove all files in $InstallDir (files may be in use). Please delete manually: $InstallDir" "WARN"
            }
        }
    }

    Write-Host @"
===============================================================================
              TechBot_Blender_MCP Uninstallation Complete!
===============================================================================
Actions Performed:
  - Blender extension package uninstalled (if present).
  - 'techbot-blender-mcp' entry removed from AI client configurations.
  - Timestamped backup files (.bak_uninstall_*) preserved in config folders.
  - Application files cleaned from: $InstallDir
===============================================================================
"@ -ForegroundColor Green

    Write-Log "Uninstallation completed successfully." "SUCCESS"
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Main
    } catch {
        Write-Log "Fatal uninstallation error: $_" "ERROR"
        exit 1
    }
}

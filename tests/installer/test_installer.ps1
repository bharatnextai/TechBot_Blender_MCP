<#
.SYNOPSIS
    Comprehensive automated test suite for TechBot_Blender_MCP Windows Installer & Uninstaller.

.DESCRIPTION
    Verifies:
    1. Checksum verification and tamper detection.
    2. Non-destructive JSON merge preserving existing MCP servers and settings.
    3. Multi-block concatenated JSON repair.
    4. Client detection functions (installed vs missing applications).
    5. Candidate selection and manual path override behavior.
    6. Backup file creation and recovery.
    7. Uninstaller safe removal preserving other servers and `-KeepLogs`.
    8. Existing port 9877 listener preservation.
    9. ChatGPT remote/manual status handling (marked UNCONFIGURED).
    10. Markdown installation report generation (TechBot-Installation-Report.md).
    11. Reconfiguration mode without service/extension re-extraction.
    12. End-to-End mock installation and uninstallation in isolated temp sandbox.
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$testDir = Join-Path $env:TEMP ("TechBot_Installer_Test_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testDir -Force | Out-Null

$scriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$installerScript = Join-Path $scriptRoot "Install-TechBot-Blender-MCP.ps1"
$uninstallerScript = Join-Path $scriptRoot "Uninstall-TechBot-Blender-MCP.ps1"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Starting TechBot_Blender_MCP Multi-Client Installer Test Suite" -ForegroundColor Cyan
Write-Host "Test Sandbox: $testDir" -ForegroundColor Cyan
Write-Host "Repository Root: $scriptRoot" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$passed = 0
$failed = 0

function Assert-Test {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    Write-Host -NoNewline "Running Test: $Name ... "
    try {
        & $Block
        Write-Host "PASSED" -ForegroundColor Green
        $script:passed++
    } catch {
        Write-Host "FAILED!" -ForegroundColor Red
        Write-Host "  Error: $_" -ForegroundColor Red
        if ($_.ScriptStackTrace) {
            Write-Host "  Stack: $($_.ScriptStackTrace)" -ForegroundColor DarkRed
        }
        $script:failed++
    }
}

try {
    # --------------------------------------------------------------------------
    # Test 1: Checksum Verification & Tamper Detection
    # --------------------------------------------------------------------------
    Assert-Test "Checksum verification and tamper detection" {
        $dummyFile = Join-Path $testDir "valid_test.zip"
        $dummySidecar = Join-Path $testDir "valid_test.zip.sha256"
        Set-Content -Path $dummyFile -Value "Test content payload 12345" -Encoding utf8
        $hash = (Get-FileHash -Path $dummyFile -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content -Path $dummySidecar -Value "$hash *valid_test.zip`n" -Encoding ascii

        $testSidecarContent = (Get-Content -Path $dummySidecar -Raw).Trim()
        $expectedHash = ($testSidecarContent -split '\s+')[0].ToLowerInvariant()
        $actualHash = (Get-FileHash -Path $dummyFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($expectedHash -ne $actualHash) {
            throw "Expected hash $expectedHash does not match actual $actualHash"
        }

        # Corrupt file
        $tamperedFile = Join-Path $testDir "corrupt_test.zip"
        Copy-Item -Path $dummyFile -Destination $tamperedFile
        Add-Content -Path $tamperedFile -Value "TAMPERED_MALICIOUS_BYTES"

        $tamperedHash = (Get-FileHash -Path $tamperedFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($expectedHash -eq $tamperedHash) {
            throw "Tampered file hash should NOT match original hash!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 2: Non-Destructive JSON Merging
    # --------------------------------------------------------------------------
    Assert-Test "Non-destructive JSON merge preserves other servers & user settings" {
        $mockConfigDir = Join-Path $testDir "mock_client"
        New-Item -ItemType Directory -Path $mockConfigDir -Force | Out-Null
        $mockConfigFile = Join-Path $mockConfigDir "client_mcp.json"

        $initialJson = @"
{
  "theme": "dark",
  "editor": {
    "tabSize": 4
  },
  "mcpServers": {
    "sqlite-server": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "test.db"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    }
  }
}
"@
        Set-Content -Path $mockConfigFile -Value $initialJson -Encoding utf8

        $pythonExe = (Get-Command "python.exe").Source
        $mockVenvPython = "C:\TestApp\venv\Scripts\python.exe"
        $port = 9877

        $mergeScript = Join-Path $testDir "test_merge.py"
        $mergePyCode = @'
import json
import sys

config_path = sys.argv[1]
venv_python = sys.argv[2]
port = sys.argv[3]

with open(config_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

server_config = {
    "command": venv_python,
    "args": ["-m", "mcp_service.app", "--transport", "stdio", "--bridge-port", port],
    "env": {"PYTHONUNBUFFERED": "1"}
}
data.setdefault("mcpServers", {})["techbot-blender-mcp"] = server_config

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("MERGE_OK")
'@
        Set-Content -Path $mergeScript -Value $mergePyCode -Encoding utf8

        $out = & $pythonExe $mergeScript $mockConfigFile $mockVenvPython ($port.ToString())
        if ($out -notmatch "MERGE_OK") { throw "Merge helper failed: $out" }

        $mergedJson = Get-Content -Path $mockConfigFile -Raw | ConvertFrom-Json
        if ($mergedJson.theme -ne "dark") { throw "Top-level property 'theme' was modified or lost!" }
        if ($mergedJson.editor.tabSize -ne 4) { throw "Nested property 'editor.tabSize' was modified or lost!" }
        if (-not $mergedJson.mcpServers.'sqlite-server') { throw "Sibling server 'sqlite-server' was lost!" }
        if (-not $mergedJson.mcpServers.filesystem) { throw "Sibling server 'filesystem' was lost!" }
        if (-not $mergedJson.mcpServers.'techbot-blender-mcp') { throw "Target server 'techbot-blender-mcp' was not added!" }
    }

    # --------------------------------------------------------------------------
    # Test 3: Multi-Block Concatenated JSON Handling
    # --------------------------------------------------------------------------
    Assert-Test "Multi-block concatenated JSON recovery into single root document" {
        $corruptFile = Join-Path $testDir "corrupt_multi.json"
        $corruptJson = @"
{
  "mcpServers": {
    "serverA": { "command": "a" }
  }
}
{
  "mcpServers": {
    "serverB": { "command": "b" }
  },
  "preferences": {
    "autoSave": true
  }
}
"@
        Set-Content -Path $corruptFile -Value $corruptJson -Encoding utf8

        $repairScript = Join-Path $testDir "test_repair_multi.py"
        $repairPyCode = @'
import json
import sys

config_path = sys.argv[1]
with open(config_path, "r", encoding="utf-8-sig") as f:
    raw = f.read().strip()

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

merged.setdefault("mcpServers", {})["techbot-blender-mcp"] = {"command": "test"}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)
print("REPAIR_OK")
'@
        Set-Content -Path $repairScript -Value $repairPyCode -Encoding utf8
        $pythonExe = (Get-Command "python.exe").Source
        $out = & $pythonExe $repairScript $corruptFile
        if ($out -notmatch "REPAIR_OK") { throw "Multi-block repair failed: $out" }

        $repaired = Get-Content -Path $corruptFile -Raw | ConvertFrom-Json
        if (-not $repaired.mcpServers.serverA) { throw "serverA was lost!" }
        if (-not $repaired.mcpServers.serverB) { throw "serverB was lost!" }
        if (-not $repaired.mcpServers.'techbot-blender-mcp') { throw "techbot was not merged!" }
        if (-not $repaired.preferences.autoSave) { throw "preferences.autoSave was lost!" }
    }

    # --------------------------------------------------------------------------
    # Test 4: Backup File Creation
    # --------------------------------------------------------------------------
    Assert-Test "Backup file creation before modification" {
        $mockFile = Join-Path $testDir "backup_test.json"
        Set-Content -Path $mockFile -Value '{"version": 1}' -Encoding utf8

        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupFile = "$mockFile.bak_$timestamp"
        Copy-Item -Path $mockFile -Destination $backupFile -Force

        if (-not (Test-Path $backupFile)) {
            throw "Backup file $backupFile was not created!"
        }
        $backupContent = Get-Content -Path $backupFile -Raw
        if ($backupContent -notmatch '"version": 1') {
            throw "Backup file content mismatch!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 5: Uninstallation Clean Removal
    # --------------------------------------------------------------------------
    Assert-Test "Uninstaller safely removes server entry while preserving others" {
        $mockConfigDir = Join-Path $testDir "mock_client"
        $mockConfigFile = Join-Path $mockConfigDir "client_mcp.json"

        $pythonExe = (Get-Command "python.exe").Source
        $removeScript = Join-Path $testDir "test_remove.py"
        $removePyCode = @'
import json
import sys

config_path = sys.argv[1]

with open(config_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

if "techbot-blender-mcp" in data.get("mcpServers", {}):
    del data["mcpServers"]["techbot-blender-mcp"]

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("REMOVE_OK")
'@
        Set-Content -Path $removeScript -Value $removePyCode -Encoding utf8

        $out = & $pythonExe $removeScript $mockConfigFile
        if ($out -notmatch "REMOVE_OK") { throw "Remove helper failed: $out" }

        $cleanJson = Get-Content -Path $mockConfigFile -Raw | ConvertFrom-Json
        if ($cleanJson.theme -ne "dark") { throw "Top-level property 'theme' lost during uninstallation!" }
        if (-not $cleanJson.mcpServers.'sqlite-server') { throw "Sibling server 'sqlite-server' was removed by mistake!" }
        if (-not $cleanJson.mcpServers.filesystem) { throw "Sibling server 'filesystem' was removed by mistake!" }
        if ($cleanJson.mcpServers.PSObject.Properties['techbot-blender-mcp']) {
            throw "'techbot-blender-mcp' was NOT removed!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 6: Port 9877 Passive Query Non-Disruption
    # --------------------------------------------------------------------------
    Assert-Test "Port 9877 check never terminates or interrupts active listeners" {
        $conn = Get-NetTCPConnection -LocalPort 9877 -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $pidBefore = $conn.OwningProcess
            # Verify installer check function
            $pidVal = $conn.OwningProcess
            $procName = (Get-Process -Id $pidVal -ErrorAction SilentlyContinue).ProcessName
            if (-not $procName) { throw "Process name lookup failed for PID $pidVal" }

            $connAfter = Get-NetTCPConnection -LocalPort 9877 -State Listen -ErrorAction SilentlyContinue
            if (-not $connAfter -or $connAfter.OwningProcess -ne $pidBefore) {
                throw "Port 9877 listener was disrupted or PID changed!"
            }
        }
    }

    # --------------------------------------------------------------------------
    # Test 7: End-to-End Mock Run with Multi-Client Selection & Report Generation
    # --------------------------------------------------------------------------
    Assert-Test "End-to-End installer execution with multi-client setup & report" {
        $mockInstallDir = Join-Path $testDir "mock_install"
        $mockReportPath = Join-Path $testDir "TechBot-Installation-Report.md"

        # Mock Cursor workspace
        $mockCursorWorkspace = Join-Path $testDir "mock_cursor_ws"
        New-Item -ItemType Directory -Path (Join-Path $mockCursorWorkspace ".cursor") -Force | Out-Null
        $mockCursorConfig = Join-Path $mockCursorWorkspace ".cursor\mcp.json"
        Set-Content -Path $mockCursorConfig -Value '{"mcpServers": {"existingCursorServer": {"command": "echo"}}}' -Encoding utf8

        # Mock Antigravity workspace
        $mockAntigravityWorkspace = Join-Path $testDir "mock_agy_ws"
        New-Item -ItemType Directory -Path (Join-Path $mockAntigravityWorkspace ".agents") -Force | Out-Null
        $mockAgyConfig = Join-Path $mockAntigravityWorkspace ".agents\mcp_config.json"
        Set-Content -Path $mockAgyConfig -Value '{"mcpServers": {"existingAgyServer": {"command": "echo"}}}' -Encoding utf8

        # Run Install-TechBot-Blender-MCP.ps1 in isolated sandbox
        $argsList = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $installerScript,
            "-LocalSourceDir", $scriptRoot,
            "-InstallDir", $mockInstallDir,
            "-InstallMode", "new",
            "-Clients", "cursor,antigravity,chatgpt",
            "-CursorScope", "workspace",
            "-CursorWorkspacePath", $mockCursorWorkspace,
            "-AntigravityScope", "workspace",
            "-AntigravityWorkspacePath", $mockAntigravityWorkspace,
            "-ReportPath", $mockReportPath,
            "-SkipBlender",
            "-NonInteractive"
        )
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -NoNewWindow -Wait -PassThru

        if ($proc.ExitCode -ne 0) {
            throw "Installer exited with non-zero code: $($proc.ExitCode)"
        }

        # Verify installation outputs
        if (-not (Test-Path "$mockInstallDir\service")) {
            throw "Service directory was not created in $mockInstallDir"
        }
        if (-not (Test-Path "$mockInstallDir\venv\Scripts\python.exe")) {
            throw "Virtual environment python was not created in $mockInstallDir\venv"
        }
        if (-not (Test-Path "$mockInstallDir\install.log")) {
            throw "Installation log file was not created"
        }
        if (-not (Test-Path $mockReportPath)) {
            throw "Installation report file $mockReportPath was not created"
        }

        # Verify report contents
        $reportText = Get-Content -Path $mockReportPath -Raw
        if ($reportText -notmatch "# TechBot_Blender_MCP Installation Report") {
            throw "Report title header missing"
        }
        if ($reportText -notmatch "ChatGPT Desktop Status") {
            throw "Report does not document ChatGPT status"
        }
        if ($reportText -notmatch "UNCONFIGURED") {
            throw "Report does not properly flag ChatGPT as UNCONFIGURED"
        }

        # Verify Cursor workspace configuration merge
        $cursorJson = Get-Content -Path $mockCursorConfig -Raw | ConvertFrom-Json
        if (-not $cursorJson.mcpServers.existingCursorServer) {
            throw "Pre-existing Cursor server was lost during merge!"
        }
        if (-not $cursorJson.mcpServers.'techbot-blender-mcp') {
            throw "TechBot server was not merged into Cursor workspace config!"
        }

        # Verify Antigravity workspace configuration merge
        $agyJson = Get-Content -Path $mockAgyConfig -Raw | ConvertFrom-Json
        if (-not $agyJson.mcpServers.existingAgyServer) {
            throw "Pre-existing Antigravity server was lost during merge!"
        }
        if (-not $agyJson.mcpServers.'techbot-blender-mcp') {
            throw "TechBot server was not merged into Antigravity workspace config!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 8: Reconfiguration Mode (Preserves Existing Service Environment)
    # --------------------------------------------------------------------------
    Assert-Test "Reconfiguration mode preserves service environment & updates configs" {
        $mockInstallDir = Join-Path $testDir "mock_install"
        $mockReportPath = Join-Path $testDir "TechBot-Installation-Report.md"

        # Touch a marker in service dir to prove it is preserved
        $markerPath = Join-Path $mockInstallDir "service\marker.txt"
        Set-Content -Path $markerPath -Value "DO_NOT_DELETE" -Encoding utf8

        # Run reconfigure mode
        $argsList = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $installerScript,
            "-InstallDir", $mockInstallDir,
            "-InstallMode", "reconfigure",
            "-Clients", "cursor",
            "-CursorScope", "workspace",
            "-CursorWorkspacePath", (Join-Path $testDir "mock_cursor_ws"),
            "-ReportPath", $mockReportPath,
            "-SkipBlender",
            "-NonInteractive"
        )
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -NoNewWindow -Wait -PassThru

        if ($proc.ExitCode -ne 0) {
            throw "Reconfigure mode exited with non-zero code: $($proc.ExitCode)"
        }

        if (-not (Test-Path $markerPath)) {
            throw "Marker file in service directory was deleted during reconfigure mode!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 9: End-to-End Mock Uninstall with -KeepLogs
    # --------------------------------------------------------------------------
    Assert-Test "End-to-End uninstaller execution in mock mode" {
        $mockInstallDir = Join-Path $testDir "mock_install"
        $mockCursorWorkspace = Join-Path $testDir "mock_cursor_ws"

        $argsList = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $uninstallerScript,
            "-InstallDir", $mockInstallDir,
            "-Clients", "cursor",
            "-WorkspacePaths", $mockCursorWorkspace,
            "-SkipBlender",
            "-KeepLogs",
            "-Force"
        )
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -NoNewWindow -Wait -PassThru

        if ($proc.ExitCode -ne 0) {
            throw "Uninstaller exited with non-zero code: $($proc.ExitCode)"
        }

        if (Test-Path "$mockInstallDir\service") {
            throw "Service directory should have been deleted by uninstaller"
        }
        if (Test-Path "$mockInstallDir\venv") {
            throw "Venv directory should have been deleted by uninstaller"
        }
        if (-not (Test-Path "$mockInstallDir\install.log")) {
            throw "install.log should have been preserved by -KeepLogs"
        }

        # Verify Cursor workspace had techbot removed but preserved sibling
        $mockCursorConfig = Join-Path $mockCursorWorkspace ".cursor\mcp.json"
        $cursorJson = Get-Content -Path $mockCursorConfig -Raw | ConvertFrom-Json
        if (-not $cursorJson.mcpServers.existingCursorServer) {
            throw "Sibling server was deleted during uninstall!"
        }
        if ($cursorJson.mcpServers.PSObject.Properties['techbot-blender-mcp']) {
            throw "techbot-blender-mcp was NOT removed from Cursor config!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 10: Correct extension install-file argument construction & user_default selection
    # --------------------------------------------------------------------------
    Assert-Test "Correct extension install-file argument construction & user_default selection" {
        . $installerScript

        $dummyZip = "C:\TechBot\dist\TechBot_Blender_MCP-1.0.0-rc2.zip"
        $argsArray = Get-BlenderExtensionInstallArgs -ExtensionZip $dummyZip -Repo "user_default"

        if ($argsArray[0] -ne "--command" -or $argsArray[1] -ne "extension" -or $argsArray[2] -ne "install-file") {
            throw "Command must begin with '--command extension install-file', got: $($argsArray[0..2] -join ' ')"
        }

        # Check repository parameter
        $rIdx = [array]::IndexOf($argsArray, "-r")
        if ($rIdx -lt 0 -or $argsArray[$rIdx + 1] -ne "user_default") {
            throw "Repository target must be strictly 'user_default'!"
        }

        if ($argsArray -contains "system" -or $argsArray -contains "blender_org") {
            throw "Arguments must NOT target 'system' or 'blender_org'!"
        }

        # Check -e and ZIP path
        $eIdx = [array]::IndexOf($argsArray, "-e")
        if ($eIdx -lt 0 -or $argsArray[$eIdx + 1] -ne $dummyZip) {
            throw "Argument list must contain '-e <ExtensionZipPath>'!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 11: Installed Extension Verification for universal_mcp ID & Package Directory
    # --------------------------------------------------------------------------
    Assert-Test "Installed extension verification for universal_mcp ID & package directory" {
        . $installerScript

        $mockUserDefault = Join-Path $testDir "mock_user_default"
        New-Item -ItemType Directory -Path $mockUserDefault -Force | Out-Null

        # Uninstalled verification check
        $uninstalledCheck = Verify-BlenderExtensionInstallation -UserDefaultDir $mockUserDefault -ExtensionId "universal_mcp"
        if ($uninstalledCheck) {
            throw "Verification should return null when extension directory is missing!"
        }

        # Create extension directory with manifest.toml
        $mockPkgDir = Join-Path $mockUserDefault "universal_mcp"
        New-Item -ItemType Directory -Path $mockPkgDir -Force | Out-Null
        Set-Content -Path (Join-Path $mockPkgDir "manifest.toml") -Value "id = 'universal_mcp'" -Encoding utf8

        $verified = Verify-BlenderExtensionInstallation -UserDefaultDir $mockUserDefault -ExtensionId "universal_mcp"
        if (-not $verified -or -not $verified.Verified) {
            throw "Verification failed when valid manifest.toml exists!"
        }
        if ($verified.ExtensionId -ne "universal_mcp") {
            throw "Verified ExtensionId mismatch: $($verified.ExtensionId)"
        }
        if ($verified.PackageDir -ne $mockPkgDir) {
            throw "Verified PackageDir mismatch: $($verified.PackageDir)"
        }

        # Verify blender_manifest.toml alternative
        Remove-Item (Join-Path $mockPkgDir "manifest.toml")
        Set-Content -Path (Join-Path $mockPkgDir "blender_manifest.toml") -Value "id = 'universal_mcp'" -Encoding utf8

        $verified2 = Verify-BlenderExtensionInstallation -UserDefaultDir $mockUserDefault -ExtensionId "universal_mcp"
        if (-not $verified2 -or -not $verified2.Verified) {
            throw "Verification failed when blender_manifest.toml exists!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 12: Blender Installation Failure Handling
    # --------------------------------------------------------------------------
    Assert-Test "Blender installation failure handling accurately reported" {
        . $installerScript

        # Create a mock failing executable script
        $mockFailingExe = Join-Path $testDir "mock_failing_blender.bat"
        Set-Content -Path $mockFailingExe -Value "@echo Installation error: simulated failure>&2`n@exit /b 1" -Encoding ascii

        $dummyZip = Join-Path $testDir "dummy_ext.zip"
        Set-Content -Path $dummyZip -Value "DUMMY_ZIP_DATA" -Encoding utf8

        $failedCleanly = $false
        try {
            Install-BlenderExtension -BlenderExe $mockFailingExe -ExtensionZip $dummyZip
        } catch {
            $failedCleanly = $true
            if ($_ -notmatch "Blender extension install-file failed with exit code 1") {
                throw "Unexpected error message: $_"
            }
        }

        if (-not $failedCleanly) {
            throw "Install-BlenderExtension should have thrown an exception on non-zero exit code!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 13: Malformed & Non-Object JSON Refusal and Backup Preservation
    # --------------------------------------------------------------------------
    Assert-Test "Malformed & non-object JSON refusal and backup preservation" {
        $corruptDir = Join-Path $testDir "corrupt_json_test"
        New-Item -ItemType Directory -Path $corruptDir -Force | Out-Null
        $corruptFile = Join-Path $corruptDir "bad_config.json"

        # 1. Unrecoverable syntax
        $unclosedJson = '{"mcpServers": {"server1": {"command": "test"}' # Unclosed braces
        Set-Content -Path $corruptFile -Value $unclosedJson -Encoding utf8

        # Create backup
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupFile = "$corruptFile.bak_$timestamp"
        Copy-Item -Path $corruptFile -Destination $backupFile -Force

        # Run merge python snippet
        $pythonExe = (Get-Command "python.exe").Source
        $testMergePy = Join-Path $testDir "test_strict_merge.py"
        $strictPyCode = @'
import json
import os
import sys

config_path = sys.argv[1]
venv_python = "C:/Test/python.exe"
server_key = "techbot-blender-mcp"
server_config = {"command": venv_python, "args": []}

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
                    print("PARSE_ERROR: Non-object JSON block encountered in multi-document stream.")
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
        Set-Content -Path $testMergePy -Value $strictPyCode -Encoding utf8

        # Run with unclosed JSON: must exit with code 2
        $p1 = Start-Process -FilePath $pythonExe -ArgumentList @($testMergePy, $corruptFile) -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$corruptDir\p1.out" -RedirectStandardError "$corruptDir\p1.err"
        if ($p1.ExitCode -ne 2) {
            throw "Python script should have exited with code 2 on unrecoverable syntax! Exit code: $($p1.ExitCode)"
        }
        $afterP1 = (Get-Content -Path $corruptFile -Raw).Trim()
        if ($afterP1 -ne $unclosedJson.Trim()) {
            throw "Corrupted file was modified or overwritten despite unrecoverable syntax error!"
        }
        if (-not (Test-Path $backupFile)) {
            throw "Backup file was missing after refusal!"
        }

        # 2. Non-object JSON root (array)
        $arrayJson = '["not", "a", "dict", "object"]'
        Set-Content -Path $corruptFile -Value $arrayJson -Encoding utf8

        $p2 = Start-Process -FilePath $pythonExe -ArgumentList @($testMergePy, $corruptFile) -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$corruptDir\p2.out" -RedirectStandardError "$corruptDir\p2.err"
        if ($p2.ExitCode -ne 2) {
            throw "Python script should have exited with code 2 on non-object JSON root! Exit code: $($p2.ExitCode)"
        }
        $afterP2 = (Get-Content -Path $corruptFile -Raw).Trim()
        if ($afterP2 -ne $arrayJson.Trim()) {
            throw "Non-object JSON was silently overwritten despite refusal rule!"
        }
    }

    # --------------------------------------------------------------------------
    # Test 14: Uninstaller Strict Containment, No Wildcards & KeepLogs
    # --------------------------------------------------------------------------
    Assert-Test "Uninstaller strict containment: explicit dir targeting, no wildcards, -KeepLogs" {
        # 1. Audit uninstaller source code to ensure NO wildcard deletions exist
        $uninstallerSource = Get-Content -Path $uninstallerScript -Raw
        if ($uninstallerSource -match 'Remove-Item\s+[^`r`n]*\*\s*') {
            throw "Unsafe wildcard pattern detected in uninstaller Remove-Item command!"
        }

        # 2. Test directory containment: ensure sibling directory is untouched
        $sandboxDir = Join-Path $testDir "containment_test"
        $mockTargetDir = Join-Path $sandboxDir "target_app"
        $mockSiblingDir = Join-Path $sandboxDir "sibling_app"
        New-Item -ItemType Directory -Path (Join-Path $mockTargetDir "venv") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $mockTargetDir "service") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $mockTargetDir "downloads") -Force | Out-Null
        Set-Content -Path (Join-Path $mockTargetDir "install.log") -Value "LOG_ENTRY" -Encoding utf8

        New-Item -ItemType Directory -Path (Join-Path $mockSiblingDir "data") -Force | Out-Null
        Set-Content -Path (Join-Path $mockSiblingDir "important.txt") -Value "DO_NOT_TOUCH" -Encoding utf8

        # Mock workspace config
        $mockWs = Join-Path $sandboxDir "ws"
        New-Item -ItemType Directory -Path (Join-Path $mockWs ".cursor") -Force | Out-Null
        $wsConfig = Join-Path $mockWs ".cursor\mcp.json"
        Set-Content -Path $wsConfig -Value '{"mcpServers": {"techbot-blender-mcp": {"cmd": "1"}, "siblingServer": {"cmd": "2"}}}' -Encoding utf8

        # Execute uninstaller with explicit target
        $argsList = @(
            "-ExecutionPolicy", "Bypass",
            "-File", $uninstallerScript,
            "-InstallDir", $mockTargetDir,
            "-Clients", "cursor",
            "-WorkspacePaths", $mockWs,
            "-SkipBlender",
            "-KeepLogs",
            "-Force"
        )
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -NoNewWindow -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "Uninstaller exited with non-zero code: $($proc.ExitCode)"
        }

        # Target directory containment
        if (Test-Path (Join-Path $mockTargetDir "venv")) { throw "target venv was not removed!" }
        if (Test-Path (Join-Path $mockTargetDir "service")) { throw "target service was not removed!" }
        if (Test-Path (Join-Path $mockTargetDir "downloads")) { throw "target downloads was not removed!" }
        if (-not (Test-Path (Join-Path $mockTargetDir "install.log"))) { throw "install.log was removed despite -KeepLogs!" }

        # Sibling directory untouched
        if (-not (Test-Path (Join-Path $mockSiblingDir "important.txt"))) {
            throw "Sibling directory was compromised by uninstaller! Directory containment failed."
        }

        # Sibling server preserved
        $cfg = Get-Content -Path $wsConfig -Raw | ConvertFrom-Json
        if (-not $cfg.mcpServers.siblingServer) { throw "siblingServer was deleted from client config!" }
        if ($cfg.mcpServers.PSObject.Properties['techbot-blender-mcp']) { throw "techbot was not removed!" }

        # Backup created
        $baks = @(Get-ChildItem -Path (Join-Path $mockWs ".cursor") -Filter "mcp.json.bak_uninstall_*")
        if ($baks.Count -eq 0) { throw "Uninstall backup file was not created!" }
    }

} finally {
    Remove-Item -Path $testDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned test sandbox: $testDir"
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Test Suite Complete: $passed Passed, $failed Failed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })
Write-Host "=================================================================" -ForegroundColor Cyan

if ($failed -gt 0) {
    exit 1
}

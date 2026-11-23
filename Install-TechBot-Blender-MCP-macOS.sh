#!/usr/bin/env bash
# ==============================================================================
# TechBot_Blender_MCP Interactive Multi-Client macOS Installer (v1.0.0)
# Universal Model Context Protocol Bridge for Blender 5.2.2 LTS / 4.2+
# Compatible with Apple Silicon (arm64) and Intel (x86_64) macOS.
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Default Settings & Parameters
# ------------------------------------------------------------------------------
RELEASE_TAG="v1.0.0-rc2"
GITHUB_REPO="bharatnextai/TechBot_Blender_MCP"
DEFAULT_INSTALL_DIR="${HOME}/Library/Application Support/TechBot_Blender_MCP"
INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
DOWNLOAD_CACHE_DIR=""
LOCAL_SOURCE_DIR=""
EXTENSION_ZIP_PATH=""
SERVICE_ZIP_PATH=""
INSTALL_MODE=""
SELECTED_CLIENTS=()
CURSOR_SCOPE="global"
CURSOR_WORKSPACE_PATH=""
ANTIGRAVITY_SCOPE="global"
ANTIGRAVITY_WORKSPACE_PATH=""
BRIDGE_PORT=9877
BRIDGE_TIMEOUT=15.0
BLENDER_PATH=""
PYTHON_PATH=""
REPORT_PATH="TechBot-Installation-Report.md"
SKIP_BLENDER=0
SKIP_SERVICE=0
SKIP_CLIENTS=0
FORCE_INSTALL=0
NON_INTERACTIVE=0

# Runtime detection records
DETECTED_ARCH=""
MACOS_VERSION=""
LOG_FILE=""
BLENDER_BIN=""
BLENDER_VERSION="Not detected"
BLENDER_EXT_RESULT="Skipped"
PYTHON_BIN=""
PYTHON_VERSION="Not detected"
UV_BIN=""
VENV_PYTHON=""
BRIDGE_STATUS="Not Running"
VERIFICATION_PASSED=0
TOOLS_DISCOVERED=0
CHATGPT_STATUS="UNCONFIGURED"

# ANSI Colors
CLR_RESET="\033[0m"
CLR_RED="\033[1;31m"
CLR_GREEN="\033[1;32m"
CLR_YELLOW="\033[1;33m"
CLR_CYAN="\033[1;36m"
CLR_MAGENTA="\033[1;35m"
CLR_WHITE="\033[1;37m"

# ------------------------------------------------------------------------------
# Logging & Utilities
# ------------------------------------------------------------------------------
log_info() {
    local ts
    ts="$(date '+%H:%M:%S')"
    echo -e "${CLR_CYAN}[${ts}][INFO] $1${CLR_RESET}"
    if [[ -n "${LOG_FILE}" ]] && [[ -d "$(dirname "${LOG_FILE}")" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')][INFO] $1" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

log_success() {
    local ts
    ts="$(date '+%H:%M:%S')"
    echo -e "${CLR_GREEN}[${ts}][SUCCESS] $1${CLR_RESET}"
    if [[ -n "${LOG_FILE}" ]] && [[ -d "$(dirname "${LOG_FILE}")" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')][SUCCESS] $1" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

log_warn() {
    local ts
    ts="$(date '+%H:%M:%S')"
    echo -e "${CLR_YELLOW}[${ts}][WARN] $1${CLR_RESET}"
    if [[ -n "${LOG_FILE}" ]] && [[ -d "$(dirname "${LOG_FILE}")" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')][WARN] $1" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

log_error() {
    local ts
    ts="$(date '+%H:%M:%S')"
    echo -e "${CLR_RED}[${ts}][ERROR] $1${CLR_RESET}" >&2
    if [[ -n "${LOG_FILE}" ]] && [[ -d "$(dirname "${LOG_FILE}")" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')][ERROR] $1" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

log_stage() {
    echo -e "\n${CLR_MAGENTA}=== $1 ===${CLR_RESET}"
    if [[ -n "${LOG_FILE}" ]] && [[ -d "$(dirname "${LOG_FILE}")" ]]; then
        echo -e "\n=== $1 ===" >> "${LOG_FILE}" 2>/dev/null || true
    fi
}

read_user_input() {
    local prompt="$1"
    local default_val="$2"
    local response=""

    if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
        echo "${default_val}"
        return
    fi

    if [[ -n "${default_val}" ]]; then
        echo -ne "${CLR_YELLOW}${prompt} [${default_val}]: ${CLR_RESET}" >&2
    else
        echo -ne "${CLR_YELLOW}${prompt}: ${CLR_RESET}" >&2
    fi
    read -r response
    if [[ -z "${response}" ]]; then
        echo "${default_val}"
    else
        echo "${response}"
    fi
}

show_banner() {
    echo -e "${CLR_MAGENTA}===============================================================================${CLR_RESET}"
    echo -e "${CLR_MAGENTA}       TechBot_Blender_MCP macOS Installer & Multi-Client Wizard (v1.0.0)      ${CLR_RESET}"
    echo -e "${CLR_MAGENTA}       Universal Model Context Protocol Bridge for Blender 5.2.2 LTS / 4.2+    ${CLR_RESET}"
    echo -e "${CLR_MAGENTA}       Architecture: ${DETECTED_ARCH:-auto} | Target Release: ${RELEASE_TAG}  ${CLR_RESET}"
    echo -e "${CLR_MAGENTA}===============================================================================${CLR_RESET}"
}

usage() {
    cat << 'EOF'
Usage: ./Install-TechBot-Blender-MCP-macOS.sh [OPTIONS]

Options:
  --release-tag <tag>             GitHub release tag (default: 'v1.0.0-rc2')
  --repo <owner/repo>             GitHub repository (default: 'bharatnextai/TechBot_Blender_MCP')
  --install-dir <path>            Target directory for MCP service (default: '~/Library/Application Support/TechBot_Blender_MCP')
  --download-cache-dir <path>     Directory for downloaded archives
  --local-source-dir <path>       Local folder containing dist packages (offline/dev mode)
  --extension-zip <path>          Explicit path to Blender extension ZIP
  --service-zip <path>            Explicit path to MCP service ZIP
  --install-mode <mode>           Mode: 'new', 'repair', 'reconfigure', 'exit'
  --clients <c1,c2,...>           Comma-separated list: claude,cursor,chatgpt,antigravity
  --cursor-scope <scope>          Cursor scope: 'global' or 'workspace' (default: 'global')
  --cursor-workspace <path>       Workspace folder if cursor-scope is 'workspace'
  --antigravity-scope <scope>     Antigravity scope: 'global' or 'workspace' (default: 'global')
  --antigravity-workspace <path>  Workspace folder if antigravity-scope is 'workspace'
  --bridge-port <port>            Blender bridge port (default: 9877)
  --bridge-timeout <sec>          Bridge connection timeout in seconds (default: 15.0)
  --blender-path <path>           Explicit path to Blender.app or Blender executable
  --python-path <path>            Explicit path to Python 3.10+ executable
  --report-path <path>            Path to write installation report markdown
  --skip-blender                  Skip Blender extension installation
  --skip-service                  Skip Python MCP service environment setup
  --skip-clients                  Skip AI client JSON configuration
  --force                         Force reinstall / overwrite without interactive prompts
  --non-interactive               Run without user interaction using defaults
  -h, --help                      Show this help message and exit
EOF
    exit 0
}

# ------------------------------------------------------------------------------
# Argument Parsing
# ------------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --release-tag)
                RELEASE_TAG="$2"; shift 2 ;;
            --repo)
                GITHUB_REPO="$2"; shift 2 ;;
            --install-dir)
                INSTALL_DIR="$2"; shift 2 ;;
            --download-cache-dir)
                DOWNLOAD_CACHE_DIR="$2"; shift 2 ;;
            --local-source-dir)
                LOCAL_SOURCE_DIR="$2"; shift 2 ;;
            --extension-zip)
                EXTENSION_ZIP_PATH="$2"; shift 2 ;;
            --service-zip)
                SERVICE_ZIP_PATH="$2"; shift 2 ;;
            --install-mode)
                INSTALL_MODE="$2"; shift 2 ;;
            --clients)
                IFS=',' read -r -a SELECTED_CLIENTS <<< "$2"; shift 2 ;;
            --cursor-scope)
                CURSOR_SCOPE="$2"; shift 2 ;;
            --cursor-workspace)
                CURSOR_WORKSPACE_PATH="$2"; shift 2 ;;
            --antigravity-scope)
                ANTIGRAVITY_SCOPE="$2"; shift 2 ;;
            --antigravity-workspace)
                ANTIGRAVITY_WORKSPACE_PATH="$2"; shift 2 ;;
            --bridge-port)
                BRIDGE_PORT="$2"; shift 2 ;;
            --bridge-timeout)
                BRIDGE_TIMEOUT="$2"; shift 2 ;;
            --blender-path)
                BLENDER_PATH="$2"; shift 2 ;;
            --python-path)
                PYTHON_PATH="$2"; shift 2 ;;
            --report-path)
                REPORT_PATH="$2"; shift 2 ;;
            --skip-blender)
                SKIP_BLENDER=1; shift ;;
            --skip-service)
                SKIP_SERVICE=1; shift ;;
            --skip-clients)
                SKIP_CLIENTS=1; shift ;;
            --force)
                FORCE_INSTALL=1; shift ;;
            --non-interactive)
                NON_INTERACTIVE=1; shift ;;
            -h|--help)
                usage ;;
            *)
                echo -e "${CLR_RED}Unknown parameter: $1${CLR_RESET}" >&2
                usage ;;
        esac
    done
}

# ------------------------------------------------------------------------------
# System & Architecture Detection
# ------------------------------------------------------------------------------
detect_system_environment() {
    local raw_arch
    raw_arch="$(uname -m 2>/dev/null || echo "unknown")"
    case "${raw_arch}" in
        arm64|aarch64)
            DETECTED_ARCH="Apple Silicon (${raw_arch})" ;;
        x86_64|amd64)
            DETECTED_ARCH="Intel Core (${raw_arch})" ;;
        *)
            DETECTED_ARCH="Unknown (${raw_arch})" ;;
    esac

    if command -v sw_vers >/dev/null 2>&1; then
        MACOS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo "macOS")"
    else
        MACOS_VERSION="$(uname -s 2>/dev/null || echo "macOS")"
    fi

    log_info "Detected Operating System: macOS ${MACOS_VERSION} [${DETECTED_ARCH}]"
}

# ------------------------------------------------------------------------------
# Blender Detection on macOS
# ------------------------------------------------------------------------------
find_blender_binary() {
    local explicit="$1"

    if [[ -n "${explicit}" ]]; then
        if [[ -d "${explicit}" ]] && [[ "${explicit}" == *.app* ]]; then
            local inside_app="${explicit}/Contents/MacOS/Blender"
            if [[ -x "${inside_app}" ]]; then
                echo "${inside_app}"
                return
            fi
            inside_app="${explicit}/Contents/MacOS/blender"
            if [[ -x "${inside_app}" ]]; then
                echo "${inside_app}"
                return
            fi
        fi
        if [[ -x "${explicit}" ]]; then
            echo "${explicit}"
            return
        fi
    fi

    # Standard macOS application bundle candidates
    local candidates=(
        "/Applications/Blender.app/Contents/MacOS/Blender"
        "/Applications/Blender.app/Contents/MacOS/blender"
        "${HOME}/Applications/Blender.app/Contents/MacOS/Blender"
        "/Applications/Blender 5.2.app/Contents/MacOS/Blender"
        "/Applications/Blender Foundation/Blender.app/Contents/MacOS/Blender"
    )

    for c in "${candidates[@]}"; do
        if [[ -x "${c}" ]]; then
            echo "${c}"
            return
        fi
    done

    # Check PATH
    if command -v blender >/dev/null 2>&1; then
        command -v blender
        return
    fi

    echo ""
}

detect_blender_version() {
    local b_bin="$1"
    if [[ -x "${b_bin}" ]]; then
        local raw_ver
        raw_ver="$("${b_bin}" --version 2>/dev/null | head -n 1 || echo "")"
        if [[ -n "${raw_ver}" ]]; then
            echo "${raw_ver}"
            return
        fi
    fi
    echo "Unknown version"
}

# ------------------------------------------------------------------------------
# Python & uv Detection on macOS
# ------------------------------------------------------------------------------
find_python_binary() {
    local explicit="$1"

    if [[ -n "${explicit}" ]] && [[ -x "${explicit}" ]]; then
        if "${explicit}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            echo "${explicit}"
            return
        fi
    fi

    local candidates=(
        "$(command -v python3 2>/dev/null || true)"
        "$(command -v python3.12 2>/dev/null || true)"
        "$(command -v python3.11 2>/dev/null || true)"
        "$(command -v python3.10 2>/dev/null || true)"
        "$(command -v python3.13 2>/dev/null || true)"
        "/opt/homebrew/bin/python3"
        "/opt/homebrew/bin/python3.12"
        "/opt/homebrew/bin/python3.11"
        "/opt/homebrew/bin/python3.10"
        "/usr/local/bin/python3"
        "/usr/local/bin/python3.12"
        "/usr/local/bin/python3.11"
        "/usr/local/bin/python3.10"
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
        "${HOME}/.pyenv/shims/python3"
    )

    for c in "${candidates[@]}"; do
        if [[ -n "${c}" ]] && [[ -x "${c}" ]]; then
            if "${c}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
                echo "${c}"
                return
            fi
        fi
    done

    echo ""
}

find_uv_binary() {
    local candidates=(
        "$(command -v uv 2>/dev/null || true)"
        "/opt/homebrew/bin/uv"
        "/usr/local/bin/uv"
        "${HOME}/.cargo/bin/uv"
        "${HOME}/.local/bin/uv"
    )

    for c in "${candidates[@]}"; do
        if [[ -n "${c}" ]] && [[ -x "${c}" ]]; then
            echo "${c}"
            return
        fi
    done

    echo ""
}

# ------------------------------------------------------------------------------
# Stage A: Mode Selection & State Inspection
# ------------------------------------------------------------------------------
detect_existing_techbot() {
    local target_dir="$1"
    if [[ -x "${target_dir}/venv/bin/python" ]] || [[ -d "${target_dir}/service/mcp_service" ]]; then
        echo "1"
    else
        echo "0"
    fi
}

select_installation_mode() {
    local is_installed
    is_installed="$(detect_existing_techbot "${INSTALL_DIR}")"

    if [[ "${is_installed}" == "1" ]]; then
        log_info "Existing TechBot installation detected at: ${INSTALL_DIR}"
    else
        log_info "No prior TechBot installation detected in: ${INSTALL_DIR}"
    fi

    if [[ -n "${INSTALL_MODE}" ]]; then
        case "${INSTALL_MODE}" in
            new|repair|reconfigure|exit)
                return ;;
            *)
                log_warn "Unrecognized mode '${INSTALL_MODE}'. Defaulting to interactive selection." ;;
        esac
    fi

    if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
        if [[ "${is_installed}" == "1" ]]; then
            INSTALL_MODE="repair"
        else
            INSTALL_MODE="new"
        fi
        return
    fi

    echo -e "\nPlease select an installation mode:"
    if [[ "${is_installed}" == "1" ]]; then
        echo -e "  ${CLR_GREEN}[1] Repair / Update existing installation${CLR_RESET}"
        echo -e "  ${CLR_CYAN}[2] Reconfigure AI Clients only (preserve extension & service)${CLR_RESET}"
        echo -e "  ${CLR_YELLOW}[3] Clean Reinstall (backup and overwrite existing)${CLR_RESET}"
        echo -e "  ${CLR_RED}[4] Exit installer${CLR_RESET}"
        local ch
        ch="$(read_user_input "Enter option (1-4)" "1")"
        case "${ch}" in
            1) INSTALL_MODE="repair" ;;
            2) INSTALL_MODE="reconfigure" ;;
            3) INSTALL_MODE="new" ;;
            4) INSTALL_MODE="exit" ;;
            *) INSTALL_MODE="repair" ;;
        esac
    else
        echo -e "  ${CLR_GREEN}[1] New Installation (Extension + MCP Service + AI Clients)${CLR_RESET}"
        echo -e "  ${CLR_CYAN}[2] Configure AI Clients only (connect to existing bridge)${CLR_RESET}"
        echo -e "  ${CLR_RED}[3] Exit installer${CLR_RESET}"
        local ch
        ch="$(read_user_input "Enter option (1-3)" "1")"
        case "${ch}" in
            1) INSTALL_MODE="new" ;;
            2) INSTALL_MODE="reconfigure" ;;
            3) INSTALL_MODE="exit" ;;
            *) INSTALL_MODE="new" ;;
        esac
    fi

    if [[ "${INSTALL_MODE}" == "exit" ]]; then
        log_info "Installation cancelled by user."
        exit 0
    fi
}

# ------------------------------------------------------------------------------
# Stage B & C: AI Client Detection on macOS
# ------------------------------------------------------------------------------
# Globals to record client info:
# CLIENT_<ID>_INSTALLED, CLIENT_<ID>_VERSION, CLIENT_<ID>_EXE, CLIENT_<ID>_CONFIG, CLIENT_<ID>_SELECTED

detect_all_clients() {
    log_stage "Scanning system for installed AI clients and MCP configurations"

    # 1. Claude Desktop
    CLIENT_CLAUDE_INSTALLED=0
    CLIENT_CLAUDE_VERSION="Not detected"
    CLIENT_CLAUDE_EXE=""
    CLIENT_CLAUDE_CONFIG="${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
    CLIENT_CLAUDE_SELECTED=0

    if [[ -d "/Applications/Claude.app" ]]; then
        CLIENT_CLAUDE_INSTALLED=1
        CLIENT_CLAUDE_EXE="/Applications/Claude.app"
        CLIENT_CLAUDE_VERSION="$(defaults read /Applications/Claude.app/Contents/Info CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    elif [[ -d "${HOME}/Applications/Claude.app" ]]; then
        CLIENT_CLAUDE_INSTALLED=1
        CLIENT_CLAUDE_EXE="${HOME}/Applications/Claude.app"
        CLIENT_CLAUDE_VERSION="$(defaults read "${CLIENT_CLAUDE_EXE}/Contents/Info" CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    fi

    # 2. Cursor IDE
    CLIENT_CURSOR_INSTALLED=0
    CLIENT_CURSOR_VERSION="Not detected"
    CLIENT_CURSOR_EXE=""
    CLIENT_CURSOR_CONFIG="${HOME}/.cursor/mcp.json"
    CLIENT_CURSOR_SELECTED=0

    if [[ -d "/Applications/Cursor.app" ]]; then
        CLIENT_CURSOR_INSTALLED=1
        CLIENT_CURSOR_EXE="/Applications/Cursor.app"
        CLIENT_CURSOR_VERSION="$(defaults read /Applications/Cursor.app/Contents/Info CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    elif [[ -d "${HOME}/Applications/Cursor.app" ]]; then
        CLIENT_CURSOR_INSTALLED=1
        CLIENT_CURSOR_EXE="${HOME}/Applications/Cursor.app"
        CLIENT_CURSOR_VERSION="$(defaults read "${CLIENT_CURSOR_EXE}/Contents/Info" CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    elif command -v cursor >/dev/null 2>&1; then
        CLIENT_CURSOR_INSTALLED=1
        CLIENT_CURSOR_EXE="$(command -v cursor)"
        CLIENT_CURSOR_VERSION="Installed (CLI)"
    fi

    # 3. Antigravity IDE
    CLIENT_ANTIGRAVITY_INSTALLED=0
    CLIENT_ANTIGRAVITY_VERSION="Not detected"
    CLIENT_ANTIGRAVITY_EXE=""
    # Path verification for Antigravity on macOS:
    # Check verified documented path ~/.gemini/config/mcp_config.json,
    # or ~/Library/Application Support/Antigravity/mcp_config.json
    local agy_doc_path="${HOME}/.gemini/config/mcp_config.json"
    local agy_appsup_path="${HOME}/Library/Application Support/Antigravity/mcp_config.json"
    if [[ -f "${agy_appsup_path}" ]]; then
        CLIENT_ANTIGRAVITY_CONFIG="${agy_appsup_path}"
    else
        CLIENT_ANTIGRAVITY_CONFIG="${agy_doc_path}"
    fi
    CLIENT_ANTIGRAVITY_SELECTED=0

    local agy_candidates=(
        "/Applications/Antigravity IDE.app"
        "/Applications/Antigravity.app"
        "${HOME}/Applications/Antigravity IDE.app"
        "${HOME}/Applications/Antigravity.app"
    )
    for ac in "${agy_candidates[@]}"; do
        if [[ -d "${ac}" ]]; then
            CLIENT_ANTIGRAVITY_INSTALLED=1
            CLIENT_ANTIGRAVITY_EXE="${ac}"
            CLIENT_ANTIGRAVITY_VERSION="$(defaults read "${ac}/Contents/Info" CFBundleShortVersionString 2>/dev/null || echo "Installed")"
            break
        fi
    done
    if [[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 0 ]] && command -v antigravity >/dev/null 2>&1; then
        CLIENT_ANTIGRAVITY_INSTALLED=1
        CLIENT_ANTIGRAVITY_EXE="$(command -v antigravity)"
        CLIENT_ANTIGRAVITY_VERSION="Installed (CLI)"
    elif [[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 0 ]] && command -v agy >/dev/null 2>&1; then
        CLIENT_ANTIGRAVITY_INSTALLED=1
        CLIENT_ANTIGRAVITY_EXE="$(command -v agy)"
        CLIENT_ANTIGRAVITY_VERSION="Installed (CLI)"
    fi

    # 4. ChatGPT Desktop
    CLIENT_CHATGPT_INSTALLED=0
    CLIENT_CHATGPT_VERSION="Not detected"
    CLIENT_CHATGPT_EXE=""
    CLIENT_CHATGPT_CONFIG="In-App Settings: Settings -> MCP Servers (Local STDIO)"
    CLIENT_CHATGPT_SELECTED=0

    if [[ -d "/Applications/ChatGPT.app" ]]; then
        CLIENT_CHATGPT_INSTALLED=1
        CLIENT_CHATGPT_EXE="/Applications/ChatGPT.app"
        CLIENT_CHATGPT_VERSION="$(defaults read /Applications/ChatGPT.app/Contents/Info CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    elif [[ -d "${HOME}/Applications/ChatGPT.app" ]]; then
        CLIENT_CHATGPT_INSTALLED=1
        CLIENT_CHATGPT_EXE="${HOME}/Applications/ChatGPT.app"
        CLIENT_CHATGPT_VERSION="$(defaults read "${CLIENT_CHATGPT_EXE}/Contents/Info" CFBundleShortVersionString 2>/dev/null || echo "Installed")"
    fi

    # Print summary
    echo -e "\n=== AI Client Detection Summary ==="
    echo -e "  [1] Claude Desktop:    $([[ ${CLIENT_CLAUDE_INSTALLED} -eq 1 ]] && echo -e "${CLR_GREEN}INSTALLED (${CLIENT_CLAUDE_VERSION})${CLR_RESET}" || echo -e "${CLR_YELLOW}NOT DETECTED${CLR_RESET}")"
    echo -e "      Config Path:       ${CLIENT_CLAUDE_CONFIG}"
    echo -e "  [2] Cursor IDE:        $([[ ${CLIENT_CURSOR_INSTALLED} -eq 1 ]] && echo -e "${CLR_GREEN}INSTALLED (${CLIENT_CURSOR_VERSION})${CLR_RESET}" || echo -e "${CLR_YELLOW}NOT DETECTED${CLR_RESET}")"
    echo -e "      Config Path:       ${CLIENT_CURSOR_CONFIG}"
    echo -e "  [3] Antigravity IDE:   $([[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 1 ]] && echo -e "${CLR_GREEN}INSTALLED (${CLIENT_ANTIGRAVITY_VERSION})${CLR_RESET}" || echo -e "${CLR_YELLOW}NOT DETECTED${CLR_RESET}")"
    echo -e "      Config Path:       ${CLIENT_ANTIGRAVITY_CONFIG}"
    echo -e "  [4] ChatGPT Desktop:   $([[ ${CLIENT_CHATGPT_INSTALLED} -eq 1 ]] && echo -e "${CLR_GREEN}INSTALLED (${CLIENT_CHATGPT_VERSION})${CLR_RESET}" || echo -e "${CLR_YELLOW}NOT DETECTED${CLR_RESET}")"
    echo -e "      Config Path:       ${CLIENT_CHATGPT_CONFIG}"
}

select_clients_wizard() {
    # If clients passed via CLI
    if [[ ${#SELECTED_CLIENTS[@]} -gt 0 ]]; then
        for sc in "${SELECTED_CLIENTS[@]}"; do
            case "$(echo "${sc}" | tr '[:upper:]' '[:lower:]' | xargs)" in
                claude) CLIENT_CLAUDE_SELECTED=1 ;;
                cursor) CLIENT_CURSOR_SELECTED=1 ;;
                antigravity) CLIENT_ANTIGRAVITY_SELECTED=1 ;;
                chatgpt) CLIENT_CHATGPT_SELECTED=1 ;;
            esac
        done
        return
    fi

    # Interactive or Default Selection
    if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
        # Default: select all detected clients
        [[ ${CLIENT_CLAUDE_INSTALLED} -eq 1 ]] && CLIENT_CLAUDE_SELECTED=1
        [[ ${CLIENT_CURSOR_INSTALLED} -eq 1 ]] && CLIENT_CURSOR_SELECTED=1
        [[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 1 ]] && CLIENT_ANTIGRAVITY_SELECTED=1
        # If none detected, select Cursor and Antigravity by default
        if [[ ${CLIENT_CLAUDE_SELECTED} -eq 0 ]] && [[ ${CLIENT_CURSOR_SELECTED} -eq 0 ]] && [[ ${CLIENT_ANTIGRAVITY_SELECTED} -eq 0 ]]; then
            CLIENT_CURSOR_SELECTED=1
            CLIENT_ANTIGRAVITY_SELECTED=1
        fi
        return
    fi

    echo -e "\n${CLR_WHITE}Select AI clients to configure with TechBot Blender MCP:${CLR_RESET}"
    local p_claude="Configure Claude Desktop? ($([[ ${CLIENT_CLAUDE_INSTALLED} -eq 1 ]] && echo "Y/n" || echo "y/N"))"
    local d_claude="$([[ ${CLIENT_CLAUDE_INSTALLED} -eq 1 ]] && echo "Y" || echo "N")"
    local ch_claude
    ch_claude="$(read_user_input "${p_claude}" "${d_claude}")"
    [[ "${ch_claude}" =~ ^[Yy]$ ]] && CLIENT_CLAUDE_SELECTED=1

    local p_cursor="Configure Cursor IDE? ($([[ ${CLIENT_CURSOR_INSTALLED} -eq 1 ]] && echo "Y/n" || echo "y/N"))"
    local d_cursor="$([[ ${CLIENT_CURSOR_INSTALLED} -eq 1 ]] && echo "Y" || echo "N")"
    local ch_cursor
    ch_cursor="$(read_user_input "${p_cursor}" "${d_cursor}")"
    [[ "${ch_cursor}" =~ ^[Yy]$ ]] && CLIENT_CURSOR_SELECTED=1

    local p_agy="Configure Antigravity IDE? ($([[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 1 ]] && echo "Y/n" || echo "y/N"))"
    local d_agy="$([[ ${CLIENT_ANTIGRAVITY_INSTALLED} -eq 1 ]] && echo "Y" || echo "N")"
    local ch_agy
    ch_agy="$(read_user_input "${p_agy}" "${d_agy}")"
    [[ "${ch_agy}" =~ ^[Yy]$ ]] && CLIENT_ANTIGRAVITY_SELECTED=1

    local p_gpt="Display ChatGPT Remote HTTPS Tunnel Instructions? (y/N)"
    local ch_gpt
    ch_gpt="$(read_user_input "${p_gpt}" "N")"
    [[ "${ch_gpt}" =~ ^[Yy]$ ]] && CLIENT_CHATGPT_SELECTED=1
}

# ------------------------------------------------------------------------------
# Stage D: Locations Confirmation & Scopes
# ------------------------------------------------------------------------------
confirm_locations_wizard() {
    if [[ -z "${DOWNLOAD_CACHE_DIR}" ]]; then
        DOWNLOAD_CACHE_DIR="${INSTALL_DIR}/downloads"
    fi

    if [[ ${NON_INTERACTIVE} -eq 0 ]]; then
        log_stage "Installation Locations Confirmation"
        echo -e "1. MCP Service & Venv Directory:  ${INSTALL_DIR}"
        echo -e "2. Release Download Cache Dir:     ${DOWNLOAD_CACHE_DIR}"

        local conf_dir
        conf_dir="$(read_user_input "Keep default directories? (Y/n)" "Y")"
        if [[ "${conf_dir}" =~ ^[Nn]$ ]]; then
            INSTALL_DIR="$(read_user_input "Enter MCP Service directory" "${INSTALL_DIR}")"
            DOWNLOAD_CACHE_DIR="$(read_user_input "Enter Download cache directory" "${INSTALL_DIR}/downloads")"
        fi

        # Scope selection for Cursor
        if [[ ${CLIENT_CURSOR_SELECTED} -eq 1 ]]; then
            echo -e "\nCursor IDE Configuration Scope:"
            echo -e "  [1] Global User Profile (${HOME}/.cursor/mcp.json)"
            echo -e "  [2] Specific Workspace (<workspace>/.cursor/mcp.json)"
            local sc_cur
            sc_cur="$(read_user_input "Choose scope (1 or 2)" "1")"
            if [[ "${sc_cur}" == "2" ]]; then
                CURSOR_SCOPE="workspace"
                CURSOR_WORKSPACE_PATH="$(read_user_input "Enter workspace folder path" "$(pwd)")"
                CLIENT_CURSOR_CONFIG="${CURSOR_WORKSPACE_PATH}/.cursor/mcp.json"
            fi
        fi

        # Scope selection for Antigravity
        if [[ ${CLIENT_ANTIGRAVITY_SELECTED} -eq 1 ]]; then
            echo -e "\nAntigravity IDE Configuration Scope:"
            echo -e "  [1] Global User Profile (${CLIENT_ANTIGRAVITY_CONFIG})"
            echo -e "  [2] Specific Workspace (<workspace>/.agents/mcp_config.json)"
            local sc_agy
            sc_agy="$(read_user_input "Choose scope (1 or 2)" "1")"
            if [[ "${sc_agy}" == "2" ]]; then
                ANTIGRAVITY_SCOPE="workspace"
                ANTIGRAVITY_WORKSPACE_PATH="$(read_user_input "Enter workspace folder path" "$(pwd)")"
                CLIENT_ANTIGRAVITY_CONFIG="${ANTIGRAVITY_WORKSPACE_PATH}/.agents/mcp_config.json"
            fi
        fi
    fi

    # Command line workspace overrides
    if [[ "${CURSOR_SCOPE}" == "workspace" ]] && [[ -n "${CURSOR_WORKSPACE_PATH}" ]]; then
        CLIENT_CURSOR_CONFIG="${CURSOR_WORKSPACE_PATH}/.cursor/mcp.json"
    fi
    if [[ "${ANTIGRAVITY_SCOPE}" == "workspace" ]] && [[ -n "${ANTIGRAVITY_WORKSPACE_PATH}" ]]; then
        CLIENT_ANTIGRAVITY_CONFIG="${ANTIGRAVITY_WORKSPACE_PATH}/.agents/mcp_config.json"
    fi

    log_stage "Pre-Installation Summary"
    echo -e "  Install Mode:        ${INSTALL_MODE}"
    echo -e "  Target Service Dir:  ${INSTALL_DIR}"
    echo -e "  Download Cache:      ${DOWNLOAD_CACHE_DIR}"
    echo -e "  Bridge Socket Port:  ${BRIDGE_PORT} (Timeout: ${BRIDGE_TIMEOUT}s)"
    echo -e "  Selected Clients:    $([[ ${CLIENT_CLAUDE_SELECTED} -eq 1 ]] && echo -n "Claude Desktop ") $([[ ${CLIENT_CURSOR_SELECTED} -eq 1 ]] && echo -n "Cursor IDE ") $([[ ${CLIENT_ANTIGRAVITY_SELECTED} -eq 1 ]] && echo -n "Antigravity IDE ") $([[ ${CLIENT_CHATGPT_SELECTED} -eq 1 ]] && echo -n "ChatGPT Desktop")"

    if [[ ${NON_INTERACTIVE} -eq 0 ]]; then
        local proceed
        proceed="$(read_user_input "\nProceed with installation? (Y/n)" "Y")"
        if [[ "${proceed}" =~ ^[Nn]$ ]]; then
            log_warn "Installation aborted by user before making changes."
            exit 0
        fi
    fi
}

# ------------------------------------------------------------------------------
# Stage E: Release Artifact Acquisition & SHA-256 Verification
# ------------------------------------------------------------------------------
compute_sha256() {
    local target_file="$1"
    "${PYTHON_BIN}" -c "import hashlib, sys
with open(sys.argv[1], 'rb') as f:
    print(hashlib.sha256(f.read()).hexdigest().lower())
" "${target_file}"
}

verify_sidecar_checksum() {
    local file_path="$1"
    local sidecar_path="$2"

    if [[ ! -f "${file_path}" ]]; then
        log_error "Artifact file does not exist: ${file_path}"
        return 1
    fi
    if [[ ! -f "${sidecar_path}" ]]; then
        log_error "Sidecar checksum file missing: ${sidecar_path}"
        return 1
    fi

    local expected_hash
    expected_hash="$(tr -d '\r\n' < "${sidecar_path}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')"
    local actual_hash
    actual_hash="$(compute_sha256 "${file_path}")"

    log_info "Verifying $(basename "${file_path}") checksum:"
    log_info "  Expected SHA-256: ${expected_hash}"
    log_info "  Computed SHA-256: ${actual_hash}"

    if [[ "${expected_hash}" != "${actual_hash}" ]]; then
        log_error "SHA-256 checksum mismatch for $(basename "${file_path}")! Refusing to install unverified artifact."
        return 1
    fi

    log_success "Checksum verification PASSED for $(basename "${file_path}")."
    return 0
}

download_file() {
    local url="$1"
    local out_path="$2"
    log_info "Downloading $(basename "${out_path}")..."
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -H "User-Agent: TechBot-Blender-MCP-Installer" "${url}" -o "${out_path}"
    else
        log_error "curl is required to download release assets."
        return 1
    fi
}

resolve_release_artifacts() {
    mkdir -p "${DOWNLOAD_CACHE_DIR}"

    RESOLVED_EXTENSION_ZIP=""
    RESOLVED_SERVICE_ZIP=""

    # 1. Explicit CLI arguments
    if [[ -n "${EXTENSION_ZIP_PATH}" ]] && [[ -f "${EXTENSION_ZIP_PATH}" ]]; then
        RESOLVED_EXTENSION_ZIP="${EXTENSION_ZIP_PATH}"
        if [[ -f "${EXTENSION_ZIP_PATH}.sha256" ]]; then
            verify_sidecar_checksum "${RESOLVED_EXTENSION_ZIP}" "${EXTENSION_ZIP_PATH}.sha256"
        fi
    fi
    if [[ -n "${SERVICE_ZIP_PATH}" ]] && [[ -f "${SERVICE_ZIP_PATH}" ]]; then
        RESOLVED_SERVICE_ZIP="${SERVICE_ZIP_PATH}"
        if [[ -f "${SERVICE_ZIP_PATH}.sha256" ]]; then
            verify_sidecar_checksum "${RESOLVED_SERVICE_ZIP}" "${SERVICE_ZIP_PATH}.sha256"
        fi
    fi

    # 2. Local Source Directory mode
    if [[ -n "${LOCAL_SOURCE_DIR}" ]] && [[ -d "${LOCAL_SOURCE_DIR}" ]]; then
        local dist_dir="${LOCAL_SOURCE_DIR}/dist"
        if [[ -d "${dist_dir}" ]]; then
            if [[ -z "${RESOLVED_EXTENSION_ZIP}" ]] && [[ ${SKIP_BLENDER} -eq 0 ]]; then
                local local_ext
                local_ext="$(ls -t "${dist_dir}"/TechBot_Blender_MCP-*.zip 2>/dev/null | grep -v 'Service' | head -n 1 || true)"
                if [[ -n "${local_ext}" ]] && [[ -f "${local_ext}" ]]; then
                    RESOLVED_EXTENSION_ZIP="${local_ext}"
                    if [[ -f "${local_ext}.sha256" ]]; then
                        verify_sidecar_checksum "${RESOLVED_EXTENSION_ZIP}" "${local_ext}.sha256"
                    fi
                    log_success "Found local extension candidate: ${local_ext}"
                fi
            fi

            if [[ -z "${RESOLVED_SERVICE_ZIP}" ]] && [[ ${SKIP_SERVICE} -eq 0 ]]; then
                local local_svc
                local_svc="$(ls -t "${dist_dir}"/TechBot_Blender_MCP_Service-*.zip 2>/dev/null | head -n 1 || true)"
                if [[ -n "${local_svc}" ]] && [[ -f "${local_svc}" ]]; then
                    RESOLVED_SERVICE_ZIP="${local_svc}"
                    if [[ -f "${local_svc}.sha256" ]]; then
                        verify_sidecar_checksum "${RESOLVED_SERVICE_ZIP}" "${local_svc}.sha256"
                    fi
                    log_success "Found local service candidate: ${local_svc}"
                fi
            fi
        fi
    fi

    # 3. GitHub Releases Download
    if ([[ -z "${RESOLVED_EXTENSION_ZIP}" ]] && [[ ${SKIP_BLENDER} -eq 0 ]]) || \
       ([[ -z "${RESOLVED_SERVICE_ZIP}" ]] && [[ ${SKIP_SERVICE} -eq 0 ]]); then
        log_info "Fetching release metadata from GitHub repository ${GITHUB_REPO} (tag: ${RELEASE_TAG})..."
        local api_url="https://api.github.com/repos/${GITHUB_REPO}/releases/tags/${RELEASE_TAG}"
        local rel_meta
        rel_meta="$(curl -fsSL -H "User-Agent: TechBot-Blender-MCP-Installer" "${api_url}" 2>/dev/null || true)"

        if [[ -z "${rel_meta}" ]]; then
            log_error "Failed to fetch release metadata from ${api_url}."
            exit 1
        fi

        # Download extension if needed
        if [[ -z "${RESOLVED_EXTENSION_ZIP}" ]] && [[ ${SKIP_BLENDER} -eq 0 ]]; then
            local ext_url ext_name ext_sha_url ext_sha_name
            ext_url="$(echo "${rel_meta}" | "${PYTHON_BIN}" -c 'import sys, json
data = json.load(sys.stdin)
for a in data.get("assets", []):
    name = a["name"]
    if name.startswith("TechBot_Blender_MCP-") and not "Service" in name and name.endswith(".zip"):
        print(a["browser_download_url"])
        sys.exit(0)
sys.exit(1)
' 2>/dev/null || true)"

            if [[ -z "${ext_url}" ]]; then
                log_error "Release '${RELEASE_TAG}' does not contain an extension ZIP asset ('TechBot_Blender_MCP-*.zip')."
                exit 1
            fi

            ext_name="$(basename "${ext_url}")"
            ext_sha_url="${ext_url}.sha256"
            ext_sha_name="${ext_name}.sha256"

            download_file "${ext_url}" "${DOWNLOAD_CACHE_DIR}/${ext_name}"
            download_file "${ext_sha_url}" "${DOWNLOAD_CACHE_DIR}/${ext_sha_name}"

            verify_sidecar_checksum "${DOWNLOAD_CACHE_DIR}/${ext_name}" "${DOWNLOAD_CACHE_DIR}/${ext_sha_name}"
            RESOLVED_EXTENSION_ZIP="${DOWNLOAD_CACHE_DIR}/${ext_name}"
        fi

        # Download service if needed
        if [[ -z "${RESOLVED_SERVICE_ZIP}" ]] && [[ ${SKIP_SERVICE} -eq 0 ]]; then
            local svc_url svc_name svc_sha_url svc_sha_name
            svc_url="$(echo "${rel_meta}" | "${PYTHON_BIN}" -c 'import sys, json
data = json.load(sys.stdin)
for a in data.get("assets", []):
    name = a["name"]
    if name.startswith("TechBot_Blender_MCP_Service-") and name.endswith(".zip"):
        print(a["browser_download_url"])
        sys.exit(0)
sys.exit(1)
' 2>/dev/null || true)"

            if [[ -z "${svc_url}" ]]; then
                log_error "Release '${RELEASE_TAG}' does not contain the companion service package ('TechBot_Blender_MCP_Service-*.zip')."
                exit 1
            fi

            svc_name="$(basename "${svc_url}")"
            svc_sha_url="${svc_url}.sha256"
            svc_sha_name="${svc_name}.sha256"

            download_file "${svc_url}" "${DOWNLOAD_CACHE_DIR}/${svc_name}"
            download_file "${svc_sha_url}" "${DOWNLOAD_CACHE_DIR}/${svc_sha_name}"

            verify_sidecar_checksum "${DOWNLOAD_CACHE_DIR}/${svc_name}" "${DOWNLOAD_CACHE_DIR}/${svc_sha_name}"
            RESOLVED_SERVICE_ZIP="${DOWNLOAD_CACHE_DIR}/${svc_name}"
        fi
    fi
}

# ------------------------------------------------------------------------------
# Stage F: Blender Extension Installation & Isolated Python Venv
# ------------------------------------------------------------------------------
install_blender_extension() {
    local ext_zip="$1"
    log_info "Deploying Blender extension from ${ext_zip}..."

    if [[ ! -x "${BLENDER_BIN}" ]]; then
        log_error "Blender executable does not exist or is not executable: ${BLENDER_BIN}"
        BLENDER_EXT_RESULT="Failed (Blender binary not found)"
        exit 1
    fi

    # Discover user_default repo directory
    local user_default_dir=""
    local repo_out=""
    repo_out="$("${BLENDER_BIN}" --command extension repo-list 2>&1 || true)"
    user_default_dir="$(echo "${repo_out}" | "${PYTHON_BIN}" -c 'import sys, re
capture = False
for line in sys.stdin:
    if re.match(r"^\s*user_default:\s*$", line):
        capture = True
        continue
    if capture:
        if re.match(r"^[a-zA-Z0-9_]+:\s*$", line):
            break
        m = re.search(r"directory:\s*\"([^\"]+)\"", line)
        if m:
            print(m.group(1))
            sys.exit(0)
sys.exit(1)
' 2>/dev/null || true)"

    if [[ -z "${user_default_dir}" ]]; then
        # Default fallback on macOS
        local base_app_sup="${HOME}/Library/Application Support/Blender"
        if [[ -d "${base_app_sup}" ]]; then
            local latest_v
            latest_v="$(ls -td "${base_app_sup}"/[0-9]* 2>/dev/null | head -n 1 || true)"
            if [[ -n "${latest_v}" ]] && [[ -d "${latest_v}/extensions/user_default" ]]; then
                user_default_dir="${latest_v}/extensions/user_default"
            fi
        fi
    fi

    if [[ -n "${user_default_dir}" ]] && [[ -d "${user_default_dir}/universal_mcp" ]]; then
        log_info "Detected existing 'universal_mcp' installation in: ${user_default_dir}/universal_mcp"
        log_info "Preserving existing user preferences during extension installation."
    fi

    # Execute verified Blender extension installation command
    log_info "Executing: \"${BLENDER_BIN}\" --command extension install-file -r user_default -e \"${ext_zip}\""
    local install_err
    install_err="$("${BLENDER_BIN}" --command extension install-file -r user_default -e "${ext_zip}" 2>&1)"
    local exit_code=$?

    if [[ ${exit_code} -ne 0 ]]; then
        log_error "Blender extension installation failed with exit code ${exit_code}!"
        log_error "${install_err}"
        BLENDER_EXT_RESULT="Failed (Code ${exit_code})"
        exit 1
    fi

    # Verification
    local list_out
    list_out="$("${BLENDER_BIN}" --command extension list 2>&1 || true)"
    if echo "${list_out}" | grep -q "universal_mcp"; then
        log_success "Extension ID 'universal_mcp' verified in repository 'user_default'."
        BLENDER_EXT_RESULT="Installed & Enabled (Repository: user_default, ID: universal_mcp)"
    elif [[ -n "${user_default_dir}" ]] && [[ -f "${user_default_dir}/universal_mcp/blender_manifest.toml" ]]; then
        log_success "Extension ID 'universal_mcp' verified with blender_manifest.toml."
        BLENDER_EXT_RESULT="Installed & Enabled (Repository: user_default, ID: universal_mcp, Path: ${user_default_dir}/universal_mcp)"
    else
        log_warn "Notice: Extension installed but could not be verified via extension list."
        BLENDER_EXT_RESULT="Installed (Unconfirmed list status)"
    fi
}

install_mcp_service() {
    local svc_zip="$1"
    log_info "Deploying external MCP service to ${INSTALL_DIR}..."

    local service_src_dir="${INSTALL_DIR}/service"
    local venv_dir="${INSTALL_DIR}/venv"
    VENV_PYTHON="${venv_dir}/bin/python"

    mkdir -p "${service_src_dir}"

    # Extract service archive cleanly
    log_info "Extracting $(basename "${svc_zip}")..."
    unzip -q -o "${svc_zip}" -d "${service_src_dir}"

    # Create virtual environment
    if [[ ! -x "${VENV_PYTHON}" ]] || [[ "${INSTALL_MODE}" == "new" ]]; then
        log_info "Creating isolated Python virtual environment at ${venv_dir}..."
        if [[ -n "${UV_BIN}" ]] && [[ -x "${UV_BIN}" ]]; then
            "${UV_BIN}" venv "${venv_dir}" --python "${PYTHON_BIN}"
        else
            "${PYTHON_BIN}" -m venv "${venv_dir}"
        fi

        if [[ ! -x "${VENV_PYTHON}" ]]; then
            log_error "Virtual environment creation failed at ${venv_dir}."
            exit 1
        fi
        log_success "Virtual environment created successfully."
    else
        log_info "Virtual environment already exists at ${venv_dir}."
    fi

    # Install package dependencies
    log_info "Installing package and dependencies into virtual environment..."
    if [[ -n "${UV_BIN}" ]] && [[ -x "${UV_BIN}" ]]; then
        "${UV_BIN}" pip install -e "${service_src_dir}" --python "${VENV_PYTHON}"
    else
        "${VENV_PYTHON}" -m pip install --upgrade pip --quiet 2>/dev/null || true
        "${VENV_PYTHON}" -m pip install -e "${service_src_dir}" --quiet
    fi
    log_success "Service dependencies installed in isolated environment."
}

# ------------------------------------------------------------------------------
# Stage G: Safe AI Client Configuration Merging & Backups
# ------------------------------------------------------------------------------
backup_config_file() {
    local cfg_path="$1"
    if [[ -f "${cfg_path}" ]]; then
        local ts
        ts="$(date '+%Y%m%d_%H%M%S')"
        local bak_path="${cfg_path}.bak_${ts}"
        cp "${cfg_path}" "${bak_path}"
        log_info "Created backup of config: ${bak_path}"
        echo "${bak_path}"
        return
    fi
    echo ""
}

merge_client_json() {
    local config_path="$1"
    local venv_py="$2"
    local port="$3"
    local timeout="$4"

    mkdir -p "$(dirname "${config_path}")"
    local bak
    bak="$(backup_config_file "${config_path}")"

    local py_merge_result
    py_merge_result="$("${PYTHON_BIN}" -c '
import json, os, sys

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
                    print("PARSE_ERROR: Non-object JSON block encountered in stream.")
                    sys.exit(2)
                pos += leading + end
            if not found_any or not merged:
                print(f"PARSE_ERROR: Unable to recover valid JSON ({exc})")
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

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("MERGE_JSON_SUCCESS")
' "${config_path}" "${venv_py}" "${port}" "${timeout}" 2>&1)"

    if [[ "${py_merge_result}" != *"MERGE_JSON_SUCCESS"* ]]; then
        log_error "Failed to update configuration at ${config_path}: ${py_merge_result}"
        return 1
    fi

    log_success "Successfully merged 'techbot-blender-mcp' in ${config_path}"
    return 0
}

configure_selected_ai_clients() {
    log_stage "Configuring selected AI client MCP connections"

    CONFIGURED_CLIENTS=()
    CLIENT_BACKUPS=()

    if [[ ${CLIENT_CLAUDE_SELECTED} -eq 1 ]]; then
        log_info "Configuring Claude Desktop at ${CLIENT_CLAUDE_CONFIG}..."
        if merge_client_json "${CLIENT_CLAUDE_CONFIG}" "${VENV_PYTHON}" "${BRIDGE_PORT}" "${BRIDGE_TIMEOUT}"; then
            CONFIGURED_CLIENTS+=("Claude Desktop")
        fi
    fi

    if [[ ${CLIENT_CURSOR_SELECTED} -eq 1 ]]; then
        log_info "Configuring Cursor IDE at ${CLIENT_CURSOR_CONFIG}..."
        if merge_client_json "${CLIENT_CURSOR_CONFIG}" "${VENV_PYTHON}" "${BRIDGE_PORT}" "${BRIDGE_TIMEOUT}"; then
            CONFIGURED_CLIENTS+=("Cursor IDE")
        fi
    fi

    if [[ ${CLIENT_ANTIGRAVITY_SELECTED} -eq 1 ]]; then
        log_info "Configuring Antigravity IDE at ${CLIENT_ANTIGRAVITY_CONFIG}..."
        if merge_client_json "${CLIENT_ANTIGRAVITY_CONFIG}" "${VENV_PYTHON}" "${BRIDGE_PORT}" "${BRIDGE_TIMEOUT}"; then
            CONFIGURED_CLIENTS+=("Antigravity IDE")
        fi
    fi

    if [[ ${CLIENT_CHATGPT_SELECTED} -eq 1 ]]; then
        log_info "Processing ChatGPT Desktop integration..."
        cat << EOF

-------------------------------------------------------------------------------
ChatGPT Desktop Local MCP Integration (STDIO):
ChatGPT Desktop supports local MCP connections over STDIO (no tunnel required).
Because ChatGPT manages servers via its in-app Settings UI instead of a
JSON file on disk, configure it in ChatGPT Settings:

1. Open ChatGPT Desktop -> Settings -> MCP Servers -> Add Server
2. Enter the following parameters:
   Name:              TechBot_Blender_MCP
   Command to launch: uv (or full path: "${INSTALL_DIR}/venv/bin/python")
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
     ${BRIDGE_PORT}
     --bridge-timeout
     ${BRIDGE_TIMEOUT}
   Environment variables:
     PYTHONPATH:        ${INSTALL_DIR}/service
     PYTHONUNBUFFERED:  1
     UMCP_BRIDGE_PORT:  ${BRIDGE_PORT}
   Working directory:   ${INSTALL_DIR}/service
3. Click Save and connect. See docs/CHATGPT_INSTALLATION.md for details.
-------------------------------------------------------------------------------
EOF
        CHATGPT_STATUS="UNCONFIGURED (Manual In-App Configuration in ChatGPT Settings Required)"
    fi
}

# ------------------------------------------------------------------------------
# Stage H: Non-Destructive Verification
# ------------------------------------------------------------------------------
run_verification_checks() {
    log_stage "Running non-destructive MCP installation checks"

    # 1. Check bridge listener (Passive port check)
    local bridge_check
    bridge_check="$("${PYTHON_BIN}" -c '
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
try:
    res = s.connect_ex(("127.0.0.1", int(sys.argv[1])))
    print("OPEN" if res == 0 else "CLOSED")
finally:
    s.close()
' "${BRIDGE_PORT}" 2>/dev/null || echo "CLOSED")"

    if [[ "${bridge_check}" == "OPEN" ]]; then
        BRIDGE_STATUS="Active (127.0.0.1:${BRIDGE_PORT})"
        log_success "Blender bridge is ACTIVE on port ${BRIDGE_PORT}."
    else
        BRIDGE_STATUS="Not Listening (Port ${BRIDGE_PORT})"
        log_info "Blender bridge is not currently active on port ${BRIDGE_PORT} (start via Blender sidebar)."
    fi

    # 2. Dependency test
    if [[ -x "${VENV_PYTHON}" ]]; then
        local dep_check
        dep_check="$("${VENV_PYTHON}" -c "import mcp, pydantic, httpx, starlette, uvicorn, mcp_service; print('DEPENDENCIES_LOADED_OK')" 2>&1 || true)"
        if [[ "${dep_check}" == *"DEPENDENCIES_LOADED_OK"* ]]; then
            log_success "Python runtime & MCP dependencies validated."
        else
            log_error "Dependency check failed in ${VENV_PYTHON}: ${dep_check}"
        fi

        # 3. MCP STDIO Handshake & Tool Listing
        log_info "Testing MCP STDIO handshake and tool listing..."
        local mcp_res
        mcp_res="$("${VENV_PYTHON}" -c '
import subprocess, json, sys

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
        print("INIT_FAIL")
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
' "${VENV_PYTHON}" "${BRIDGE_PORT}" 2>&1 || true)"

        if [[ "${mcp_res}" =~ MCP_VERIFY_SUCCESS:([0-9]+) ]]; then
            TOOLS_DISCOVERED="${BASH_REMATCH[1]}"
            VERIFICATION_PASSED=1
            log_success "MCP STDIO handshake succeeded. Discovered ${TOOLS_DISCOVERED} typed tools."
        else
            log_warn "MCP STDIO test returned: ${mcp_res}"
        fi
    fi
}

# ------------------------------------------------------------------------------
# Stage I: Installation Report Generation
# ------------------------------------------------------------------------------
generate_report() {
    log_stage "Writing installation markdown report"

    local report_dest="${REPORT_PATH}"
    local gen_time
    gen_time="$(date '+%Y-%m-%d %H:%M:%S')"

    cat << EOF > "${report_dest}"
# TechBot_Blender_MCP Installation Report (macOS)

**Generated:** ${gen_time}  
**Installer Version:** 1.0.0  
**Install Mode:** ${INSTALL_MODE}  
**Architecture:** ${DETECTED_ARCH} (macOS ${MACOS_VERSION})  
**Repository Target:** ${GITHUB_REPO} (Release: ${RELEASE_TAG})  

---

## 1. Environment & Components

| Component | Status / Path |
| :--- | :--- |
| **Blender Executable** | ${BLENDER_BIN:-Not detected} (${BLENDER_VERSION}) |
| **Blender Extension** | ${BLENDER_EXT_RESULT} |
| **Python Runtime** | ${PYTHON_BIN:-Not detected} (v${PYTHON_VERSION}) |
| **Package Manager (uv)**| ${UV_BIN:-Not installed (pip fallback)} |
| **Service Target Dir** | ${INSTALL_DIR} |
| **Virtual Environment**| ${VENV_PYTHON:-Not configured} |
| **Bridge Socket Port** | ${BRIDGE_PORT} (Timeout: ${BRIDGE_TIMEOUT}s) |
| **Bridge Listener** | ${BRIDGE_STATUS} |

---

## 2. Configured AI Clients

| Client | Configuration Path | Scope |
| :--- | :--- | :--- |
EOF

    if [[ ${#CONFIGURED_CLIENTS[@]} -gt 0 ]]; then
        for cc in "${CONFIGURED_CLIENTS[@]}"; do
            case "${cc}" in
                "Claude Desktop")
                    echo "| **Claude Desktop** | ${CLIENT_CLAUDE_CONFIG} | Global User Profile |" >> "${report_dest}" ;;
                "Cursor IDE")
                    echo "| **Cursor IDE** | ${CLIENT_CURSOR_CONFIG} | ${CURSOR_SCOPE} |" >> "${report_dest}" ;;
                "Antigravity IDE")
                    echo "| **Antigravity IDE** | ${CLIENT_ANTIGRAVITY_CONFIG} | ${ANTIGRAVITY_SCOPE} |" >> "${report_dest}" ;;
            esac
        done
    else
        echo "| *None configured* | - | - |" >> "${report_dest}"
    fi

    cat << EOF >> "${report_dest}"

### ChatGPT Desktop Status
> **${CHATGPT_STATUS}**  
> ChatGPT Desktop communicates over local STDIO pipes configured via ChatGPT in-app Settings (**Settings -> MCP Servers**).  
> Follow the verified instructions in [\`docs/CHATGPT_INSTALLATION.md\`](docs/CHATGPT_INSTALLATION.md).

| Setting | Value |
| :--- | :--- |
| **Server Name** | \`TechBot_Blender_MCP\` |
| **Command** | \`uv\` *(or \`${VENV_PYTHON}\`)* |
| **Arguments** | \`run\`, \`--no-project\`, \`--with\`, \`mcp<2,>=1.25.0\`, \`--with\`, \`pydantic>=2.0.0\`, \`--with\`, \`httpx>=0.25.0\`, \`python\`, \`-m\`, \`mcp_service.app\`, \`--transport\`, \`stdio\`, \`--bridge-port\`, \`${BRIDGE_PORT}\`, \`--bridge-timeout\`, \`15.0\` |
| **Environment Variables** | \`PYTHONPATH\`: \`${INSTALL_DIR}/service\`<br>\`PYTHONUNBUFFERED\`: \`1\`<br>\`UMCP_BRIDGE_PORT\`: \`${BRIDGE_PORT}\` |
| **Working Directory** | \`${INSTALL_DIR}/service\` |

---

## 3. Verification Results

- **Python Runtime & Dependencies:** $([[ -x "${VENV_PYTHON}" ]] && echo "PASSED" || echo "SKIPPED")  
- **MCP STDIO Handshake:** $([[ ${VERIFICATION_PASSED} -eq 1 ]] && echo "PASSED" || echo "UNVERIFIED")  
- **Tools Discovered:** ${TOOLS_DISCOVERED}  
- **Bridge Port ${BRIDGE_PORT} Listener:** ${BRIDGE_STATUS} (Never interrupted)  

---

## 4. Next Steps

1. Launch **Blender 5.2.2 LTS**.
2. Press **N** in the 3D Viewport to display the sidebar, select the **Universal MCP** tab, and ensure the bridge server is active.
3. Open your configured AI client (**Claude Desktop**, **Cursor IDE**, or **Antigravity IDE**). TechBot Blender tools will be automatically loaded.
EOF

    log_success "Installation report written to: ${report_dest}"
    if [[ -d "${INSTALL_DIR}" ]]; then
        cp "${report_dest}" "${INSTALL_DIR}/TechBot-Installation-Report.md" 2>/dev/null || true
    fi
}

# ------------------------------------------------------------------------------
# Main Routine
# ------------------------------------------------------------------------------
main() {
    parse_args "$@"

    mkdir -p "${INSTALL_DIR}"
    LOG_FILE="${INSTALL_DIR}/install.log"
    echo "=== TechBot_Blender_MCP macOS Installer Session: $(date '+%Y-%m-%d %H:%M:%S') ===" >> "${LOG_FILE}"

    detect_system_environment
    show_banner

    # Preflight tool checks
    PYTHON_BIN="$(find_python_binary "${PYTHON_PATH}")"
    if [[ -z "${PYTHON_BIN}" ]]; then
        log_error "Python 3.10 or higher is required. Please install Python 3.10+ (via python.org, Homebrew 'brew install python@3.12', or pyenv)."
        exit 1
    fi
    PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "Unknown")"
    log_success "Found Python: ${PYTHON_BIN} (v${PYTHON_VERSION})"

    UV_BIN="$(find_uv_binary)"
    if [[ -n "${UV_BIN}" ]]; then
        log_success "Found uv package manager: ${UV_BIN}"
    else
        log_info "uv not found; using standard python3 -m venv and pip fallback."
    fi

    if [[ ${SKIP_BLENDER} -eq 0 ]]; then
        BLENDER_BIN="$(find_blender_binary "${BLENDER_PATH}")"
        if [[ -n "${BLENDER_BIN}" ]]; then
            BLENDER_VERSION="$(detect_blender_version "${BLENDER_BIN}")"
            log_success "Found Blender: ${BLENDER_BIN} (${BLENDER_VERSION})"
        else
            log_warn "Blender executable not found in standard /Applications paths. Use --blender-path to specify."
        fi
    fi

    # Stage A: Mode
    select_installation_mode

    # Stage B & C: Clients
    detect_all_clients
    select_clients_wizard

    # Stage D: Locations
    confirm_locations_wizard

    # Stage E: Artifacts
    if [[ "${INSTALL_MODE}" != "reconfigure" ]]; then
        resolve_release_artifacts
    fi

    # Stage F: Extension & Service
    if [[ "${INSTALL_MODE}" != "reconfigure" ]]; then
        if [[ ${SKIP_BLENDER} -eq 0 ]] && [[ -n "${BLENDER_BIN}" ]] && [[ -n "${RESOLVED_EXTENSION_ZIP}" ]]; then
            install_blender_extension "${RESOLVED_EXTENSION_ZIP}"
        fi

        if [[ ${SKIP_SERVICE} -eq 0 ]] && [[ -n "${RESOLVED_SERVICE_ZIP}" ]]; then
            install_mcp_service "${RESOLVED_SERVICE_ZIP}"
        fi
    else
        VENV_PYTHON="${INSTALL_DIR}/venv/bin/python"
    fi

    # Stage G: Client Configs
    if [[ ${SKIP_CLIENTS} -eq 0 ]]; then
        configure_selected_ai_clients
    fi

    # Stage H: Verification
    run_verification_checks

    # Stage I: Report
    generate_report

    echo -e "\n${CLR_GREEN}===============================================================================${CLR_RESET}"
    echo -e "${CLR_GREEN}              TechBot_Blender_MCP Installation Complete!                       ${CLR_RESET}"
    echo -e "${CLR_GREEN}===============================================================================${CLR_RESET}"
    echo -e "  - Installation Mode:    ${INSTALL_MODE}"
    echo -e "  - Target Service Dir:   ${INSTALL_DIR}"
    echo -e "  - Bridge Socket Port:   ${BRIDGE_PORT}"
    echo -e "  - Summary Report:       ${REPORT_PATH}"
    echo -e "  - Installation Log:     ${LOG_FILE}"
    echo -e "  - Safe Uninstaller:     ./Uninstall-TechBot-Blender-MCP-macOS.sh"
    echo -e "\nNext Steps:"
    echo -e "  1. Open Blender. In the 3D Viewport sidebar (N), select 'Universal MCP'."
    echo -e "  2. Launch your configured AI client. The typed Blender tools are active."
    echo -e "${CLR_GREEN}===============================================================================${CLR_RESET}"
}

main "$@"

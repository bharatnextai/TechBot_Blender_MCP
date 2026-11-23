#!/usr/bin/env bash
# ==============================================================================
# TechBot_Blender_MCP Production Uninstaller for macOS (v1.0.0)
# Safely removes TechBot_Blender_MCP components and cleans client configurations.
# ==============================================================================

set -euo pipefail

DEFAULT_INSTALL_DIR="${HOME}/Library/Application Support/TechBot_Blender_MCP"
INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
SELECTED_CLIENTS=("claude" "cursor" "antigravity" "chatgpt")
WORKSPACE_PATHS=()
CHATGPT_CONFIG_PATH=""
BLENDER_PATH=""
SKIP_BLENDER=0
KEEP_LOGS=0
FORCE_UNINSTALL=0
NON_INTERACTIVE=0
LOG_FILE=""

CLR_RESET="\033[0m"
CLR_RED="\033[1;31m"
CLR_GREEN="\033[1;32m"
CLR_YELLOW="\033[1;33m"
CLR_CYAN="\033[1;36m"
CLR_MAGENTA="\033[1;35m"

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

show_banner() {
    echo -e "${CLR_MAGENTA}===============================================================================${CLR_RESET}"
    echo -e "${CLR_MAGENTA}       TechBot_Blender_MCP macOS Uninstaller                                   ${CLR_RESET}"
    echo -e "${CLR_MAGENTA}       Target Application Directory: ${INSTALL_DIR}                           ${CLR_RESET}"
    echo -e "${CLR_MAGENTA}===============================================================================${CLR_RESET}"
}

usage() {
    cat << 'EOF'
Usage: ./Uninstall-TechBot-Blender-MCP-macOS.sh [OPTIONS]

Options:
  --install-dir <path>            Target directory for MCP service (default: '~/Library/Application Support/TechBot_Blender_MCP')
  --clients <c1,c2,...>           Comma-separated AI clients to clean: claude,cursor,antigravity,chatgpt
  --workspace-paths <w1,w2,...>   Workspace directories to clean workspace-level configs
  --chatgpt-config-path <path>    Explicit path to ChatGPT/Codex config.toml
  --blender-path <path>           Explicit path to Blender.app or executable
  --skip-blender                  Skip removing extension from Blender
  --keep-logs                     Preserve logs in application directory
  --force                         Bypass confirmation prompt
  --non-interactive               Non-interactive mode
  -h, --help                      Show this help message and exit
EOF
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --install-dir)
                INSTALL_DIR="$2"; shift 2 ;;
            --clients)
                IFS=',' read -r -a SELECTED_CLIENTS <<< "$2"; shift 2 ;;
            --workspace-paths)
                IFS=',' read -r -a WORKSPACE_PATHS <<< "$2"; shift 2 ;;
            --chatgpt-config-path)
                CHATGPT_CONFIG_PATH="$2"; shift 2 ;;
            --blender-path)
                BLENDER_PATH="$2"; shift 2 ;;
            --skip-blender)
                SKIP_BLENDER=1; shift ;;
            --keep-logs)
                KEEP_LOGS=1; shift ;;
            --force)
                FORCE_UNINSTALL=1; shift ;;
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

find_blender_binary() {
    local explicit="$1"
    if [[ -n "${explicit}" ]]; then
        if [[ -d "${explicit}" ]] && [[ "${explicit}" == *.app* ]]; then
            local inside_app="${explicit}/Contents/MacOS/Blender"
            [[ -x "${inside_app}" ]] && echo "${inside_app}" && return
            inside_app="${explicit}/Contents/MacOS/blender"
            [[ -x "${inside_app}" ]] && echo "${inside_app}" && return
        fi
        if [[ -x "${explicit}" ]]; then
            echo "${explicit}"
            return
        fi
    fi

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

    if command -v blender >/dev/null 2>&1; then
        command -v blender
        return
    fi

    echo ""
}

find_python() {
    if [[ -x "${INSTALL_DIR}/venv/bin/python" ]]; then
        echo "${INSTALL_DIR}/venv/bin/python"
        return
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return
    fi
    echo ""
}

uninstall_blender_extension() {
    local b_bin="$1"
    log_info "Uninstalling Blender extension 'universal_mcp'..."
    local uninst_out
    uninst_out="$("${b_bin}" --command extension remove universal_mcp 2>&1 || true)"
    if echo "${uninst_out}" | grep -qi "removed\|success\|not found"; then
        log_success "Blender extension removed successfully."
    else
        log_warn "Blender extension removal returned: ${uninst_out}"
    fi
}

remove_client_server_entry() {
    local cfg_path="$1"
    local py_bin="$2"

    if [[ ! -f "${cfg_path}" ]]; then
        return
    fi

    log_info "Cleaning MCP configuration from ${cfg_path}..."

    # Create timestamped backup
    local ts
    ts="$(date '+%Y%m%d_%H%M%S')"
    local bak="${cfg_path}.bak_uninstall_${ts}"
    cp "${cfg_path}" "${bak}"
    log_info "Created backup at ${bak}"

    if [[ -n "${py_bin}" ]] && [[ -x "${py_bin}" ]]; then
        local res
        if [[ "${cfg_path}" == *.toml ]]; then
            res="$("${py_bin}" -c '
import os, re, sys

config_path = sys.argv[1]
server_key = "techbot-blender-mcp"

if not os.path.isfile(config_path):
    print("NO_FILE")
    sys.exit(0)

try:
    with open(config_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
except Exception as exc:
    print(f"PARSE_ERROR:{exc}")
    sys.exit(1)

lines = content.splitlines()
out = []
skip = False
removed = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("["):
        m = re.match(r"^\[\s*mcp_servers\.[\"'\x27]?techbot[-_]blender[-_]mcp[\"'\x27]?(\.|\s*\])", stripped)
        if m:
            skip = True
            removed = True
            continue
        else:
            skip = False
    if not skip:
        out.append(line)

final_content = "\n".join(out).rstrip() + "\n"
with open(config_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(final_content)

if removed:
    print(f"REMOVED_KEY:{server_key} CLEAN_JSON_SUCCESS")
else:
    print(f"KEY_NOT_FOUND:{server_key} CLEAN_JSON_SUCCESS")
' "${cfg_path}" 2>&1)"
        else
            res="$("${py_bin}" -c '
import json, os, sys

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

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("CLEAN_JSON_SUCCESS")
' "${cfg_path}" 2>&1)"
        fi
        log_success "Client config cleanup result: ${res}"
    else
        log_warn "Python not available to clean config cleanly. Please remove 'techbot-blender-mcp' manually from ${cfg_path}"
    fi
}

cleanup_ai_clients() {
    local py_bin
    py_bin="$(find_python)"

    local targets=()

    for c in "${SELECTED_CLIENTS[@]}"; do
        case "$(echo "${c}" | tr '[:upper:]' '[:lower:]' | xargs)" in
            claude)
                targets+=("${HOME}/Library/Application Support/Claude/claude_desktop_config.json")
                ;;
            cursor)
                targets+=("${HOME}/.cursor/mcp.json")
                ;;
            antigravity)
                targets+=("${HOME}/.gemini/config/mcp_config.json")
                targets+=("${HOME}/Library/Application Support/Antigravity/mcp_config.json")
                ;;
            chatgpt)
                targets+=("${CHATGPT_CONFIG_PATH:-${HOME}/.codex/config.toml}")
                ;;
        esac
    done

    # Workspace configurations
    for ws in "${WORKSPACE_PATHS[@]}"; do
        if [[ -d "${ws}" ]]; then
            targets+=("${ws}/.cursor/mcp.json")
            targets+=("${ws}/.agents/mcp_config.json")
        fi
    done

    for t in "${targets[@]}"; do
        if [[ -f "${t}" ]]; then
            remove_client_server_entry "${t}" "${py_bin}"
        fi
    done
}

cleanup_install_directory() {
    if [[ ! -d "${INSTALL_DIR}" ]]; then
        return
    fi

    log_info "Cleaning application directory: ${INSTALL_DIR}..."

    if [[ ${KEEP_LOGS} -eq 1 ]]; then
        local subdirs=("venv" "service" "downloads")
        for sub in "${subdirs[@]}"; do
            local p="${INSTALL_DIR}/${sub}"
            if [[ -d "${p}" ]]; then
                rm -rf "${p}"
                log_info "Removed ${p}"
            fi
        done
        log_info "Preserved log files in ${INSTALL_DIR}"
    else
        rm -rf "${INSTALL_DIR}"
        log_success "Removed application directory: ${INSTALL_DIR}"
    fi
}

main() {
    parse_args "$@"

    if [[ -d "${INSTALL_DIR}" ]]; then
        LOG_FILE="${INSTALL_DIR}/uninstall.log"
    fi

    show_banner

    if [[ ${FORCE_UNINSTALL} -eq 0 ]] && [[ ${NON_INTERACTIVE} -eq 0 ]]; then
        echo -e "${CLR_YELLOW}This will remove TechBot_Blender_MCP components and MCP configurations.${CLR_RESET}"
        echo -ne "${CLR_YELLOW}Are you sure you want to proceed? (y/N): ${CLR_RESET}"
        read -r resp
        if [[ ! "${resp}" =~ ^[Yy]$ ]]; then
            log_info "Uninstallation cancelled by user."
            exit 0
        fi
    fi

    # 1. Blender Extension removal
    if [[ ${SKIP_BLENDER} -eq 0 ]]; then
        local b_bin
        b_bin="$(find_blender_binary "${BLENDER_PATH}")"
        if [[ -n "${b_bin}" ]]; then
            uninstall_blender_extension "${b_bin}"
        else
            log_warn "Blender executable not found. Skipping Blender extension uninstallation."
        fi
    fi

    # 2. Client Configurations
    cleanup_ai_clients

    # 3. Application Directory
    cleanup_install_directory

    echo -e "\n${CLR_GREEN}===============================================================================${CLR_RESET}"
    echo -e "${CLR_GREEN}              TechBot_Blender_MCP Uninstallation Complete!                     ${CLR_RESET}"
    echo -e "${CLR_GREEN}===============================================================================${CLR_RESET}"
    echo -e "Actions Performed:"
    echo -e "  - Blender extension package uninstalled (if present)."
    echo -e "  - 'techbot-blender-mcp' entry removed from AI client configurations."
    echo -e "  - Timestamped backup files (.bak_uninstall_*) preserved in config folders."
    echo -e "  - Application files cleaned from: ${INSTALL_DIR}"
    echo -e "${CLR_GREEN}===============================================================================${CLR_RESET}"
}

main "$@"

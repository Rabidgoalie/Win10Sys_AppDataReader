#!/usr/bin/env bash
# =============================================================================
# setup.sh — Bootstrap for the Windows 10 Disaster Recovery Application
# =============================================================================
#
# Responsibilities (SDD 2.1):
#   * Detect that we are on Linux.
#   * Detect Ubuntu 24.04 / Pop!_OS 24.04 / compatible environments.
#   * Require a Python 3.12-series interpreter (>= 3.12.0, < 3.13.0).
#   * Verify python3-venv, Tkinter, and the required host tools.
#   * Create or reuse the app-owned venv "Win10DRBPythonVenv".
#   * Install runtime Python dependencies into that venv only.
#
# Safety boundaries (ADR-2, ADR-11, SRS 2.3, SRS 3.1):
#   * NEVER installs host/system packages automatically. When a host package
#     is missing, we print the exact manual command and exit without changes.
#   * NEVER touches any source drive: no mounting, no scanning, no writes to
#     any scanned media. This script operates only on the host and the project.
#   * Writes only to the app-owned venv directory and standard pip caches.
#   * External tools are invoked as argument vectors, never via a shell
#     interpreter (no `eval`, no `sh -c`).
#   * Does NOT require or reference Conda. Does NOT require git.
#
# Exit codes:
#   0  success
#   1  environment not ready (actionable guidance printed)
#   2  unexpected / internal error
#
# NOTE on `set -e`: we intentionally do NOT use `-e`. A bootstrap should
# aggregate every missing prerequisite into one calm, complete report rather
# than stopping at the first gap. We therefore check every condition
# explicitly and exit ourselves.
#
# shellcheck disable=SC2310

set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly VENV_NAME="Win10DRBPythonVenv"
readonly REQUIREMENTS_FILE="requirements.txt"

# Resolve the project root from the script location so the script works
# regardless of the caller's current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/${VENV_NAME}"
VENV_PY="${VENV_DIR}/bin/python"
REQUIREMENTS="${SCRIPT_DIR}/${REQUIREMENTS_FILE}"

# ---------------------------------------------------------------------------
# Calm, color-aware logging (respects NO_COLOR and non-TTY output)
# ---------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  R_INFO=$'\033[0;36m'; R_OK=$'\033[0;32m'; R_WARN=$'\033[0;33m'
  R_ERR=$'\033[0;31m';  R_BOLD=$'\033[1m';  R_RESET=$'\033[0m'
else
  R_INFO=""; R_OK=""; R_WARN=""; R_ERR=""; R_BOLD=""; R_RESET=""
fi

log_info()  { printf '%s * %s%s\n'  "$R_INFO" "$*" "$R_RESET"; }
log_ok()    { printf '%s[ok]%s %s%s\n'  "$R_OK" "$R_RESET" "$*" "$R_RESET"; }
log_warn()  { printf '%s[!] %s%s\n'   "$R_WARN" "$*" "$R_RESET"; }
log_error() { printf '%s[x]%s %s%s\n'  "$R_ERR" "$R_RESET" "$*" "$R_RESET" >&2; }
log_title() { printf '\n%s%s%s\n' "$R_BOLD" "$*" "$R_RESET"; }

# Graceful, non-blaming interruption: no host packages have been changed yet.
on_interrupt() {
  printf '\n%sInterrupted. No host packages were changed.%s\n' "$R_WARN" "$R_RESET"
  printf 'Run this script again to continue.\n'
  exit 130
}
trap on_interrupt INT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
has_cmd() { command -v "$1" >/dev/null 2>&1; }

# True when VERSION matches the required 3.12-series range (3.12.x).
python_is_312() { [[ "${1:-}" =~ ^3\.12\.[0-9]+$ ]]; }

# Print the version an interpreter reports as major.minor.micro (empty on error).
py_report_version() {
  "$1" -c 'import sys; print(".".join(str(x) for x in sys.version_info[:3]))' 2>/dev/null || true
}

# Print the absolute path to a Python 3.12.x interpreter on PATH, if any.
find_python312() {
  local candidate path ver
  for candidate in python3.12 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    path="$(command -v "$candidate")"
    ver="$(py_report_version "$path")"
    if python_is_312 "$ver"; then
      printf '%s' "$path"
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Missing-item collector (aggregate, then report once)
# ---------------------------------------------------------------------------
MISSING_LABELS=()
MISSING_FIXES=()
WANTED_PKGS=()      # ordered host package names for a convenience one-liner
add_missing() {
  MISSING_LABELS+=("$1")
  MISSING_FIXES+=("$2")
  if [[ $# -ge 3 ]]; then
    WANTED_PKGS+=("$3")
  fi
}

# ===========================================================================
# [1] Linux
# ===========================================================================
log_title "Windows 10 Disaster Recovery — setup"
log_info "Checking your environment. This will not change any system packages."
log_info "If something is missing, I will tell you exactly how to install it."

uname_s="$(uname -s 2>/dev/null || true)"
if [[ "$uname_s" != "Linux" ]]; then
  log_error "This script is meant to run on Linux."
  log_error "Detected operating system: ${uname_s:-unknown}."
  log_error "Please run it on an Ubuntu 24.04 Live Session or Pop!_OS 24.04."
  exit 1
fi
log_ok "Operating system: Linux"

# ===========================================================================
# [2] Distribution
# ===========================================================================
# Sourced in a subshell so we do not pollute this script's environment.
DISTRO_ID=""; DISTRO_VER=""; DISTRO_LIKE=""
if [[ -r /etc/os-release ]]; then
  DISTRO_ID="$(   . /etc/os-release 2>/dev/null; printf '%s' "${ID:-}" )"
  DISTRO_VER="$(  . /etc/os-release 2>/dev/null; printf '%s' "${VERSION_ID:-}" )"
  DISTRO_LIKE="$( . /etc/os-release 2>/dev/null; printf '%s' "${ID_LIKE:-}" )"
fi

if [[ "$DISTRO_ID" == "ubuntu" && "$DISTRO_VER" == "24.04" ]]; then
  log_ok "Distribution: Ubuntu 24.04 (primary supported environment)"
elif [[ "$DISTRO_ID" == "pop" ]]; then
  log_ok "Distribution: Pop!_OS ${DISTRO_VER:-?} (supported, Ubuntu-based)"
elif [[ "$DISTRO_LIKE" == *ubuntu* || "$DISTRO_LIKE" == *debian* || "$DISTRO_ID" == "debian" ]]; then
  log_warn "Distribution: ${DISTRO_ID:-unknown} ${DISTRO_VER:-?} (compatible; best-effort support)"
else
  log_error "Distribution: ${DISTRO_ID:-unknown} ${DISTRO_VER:-?}"
  log_error "This is not a supported Ubuntu 24.04 / Pop!_OS 24.04 environment."
  log_error "The package instructions in this tool assume Ubuntu/Debian."
  log_error "Please run the app on Ubuntu 24.04 Live Session or Pop!_OS 24.04."
  exit 1
fi

# The app is designed to run as the normal desktop user. A root-owned venv would
# be unusable by that user, so surface it clearly (warning, not a hard block).
if [[ "$(id -u 2>/dev/null || echo '?')" == "0" ]]; then
  log_warn "You appear to be running as root."
  log_warn "The app is intended to run as your normal desktop user, and the virtual environment should be owned by that user."
  log_warn "You may continue, but re-running this script as your normal user is recommended."
fi

# ===========================================================================
# [3] Required host tools (validated but NOT installed by this script)
# ===========================================================================
log_title "Checking required host tools"

util_missing=()
for tool in lsblk mount umount; do
  has_cmd "$tool" || util_missing+=("$tool")
done
if (( ${#util_missing[@]} )); then
  add_missing "util-linux tools: ${util_missing[*]}" \
              "sudo apt update && sudo apt install -y util-linux" "util-linux"
else
  log_ok "util-linux tools present (lsblk, mount, umount)"
fi

ntfs_missing=()
for tool in ntfs-3g ntfsls; do
  has_cmd "$tool" || ntfs_missing+=("$tool")
done
if (( ${#ntfs_missing[@]} )); then
  add_missing "ntfs-3g tools: ${ntfs_missing[*]}" \
              "sudo apt update && sudo apt install -y ntfs-3g" "ntfs-3g"
else
  log_ok "ntfs-3g tools present (ntfs-3g, ntfsls)"
fi

# ===========================================================================
# [4] Python 3.12-series
# ===========================================================================
log_title "Checking Python"

python_present=0
pybin=""
pyver=""
if pybin="$(find_python312)"; then
  python_present=1
  pyver="$(py_report_version "$pybin")"
  log_ok "Python ${pyver} found at ${pybin}"
else
  add_missing "Python 3.12-series interpreter (>= 3.12.0, < 3.13.0)" \
              "sudo apt update && sudo apt install -y python3.12"
  log_warn "No Python 3.12-series interpreter was found."
fi

# ===========================================================================
# [5] python3-venv + Tkinter (only checkable when a usable Python exists)
# ===========================================================================
if [[ "$python_present" == 1 ]]; then
  # python3-venv ships the pip bootstrap wheels under ensurepip/_bundled.
  # Probing that directory is a reliable way to detect a missing python3-venv
  # even though `import ensurepip` alone would still succeed.
  wheel_dir="$("$pybin" -c 'import os, ensurepip; print(os.path.join(os.path.dirname(ensurepip.__file__), "_bundled"))' 2>/dev/null || true)"
  if [[ -n "$wheel_dir" && -d "$wheel_dir" ]] && ls "$wheel_dir"/*.whl >/dev/null 2>&1; then
    log_ok "python3-venv bootstrap wheels present"
  else
    add_missing "python3-venv (pip bootstrap wheels)" \
                "sudo apt update && sudo apt install -y python3-venv" "python3-venv"
    log_warn "python3-venv does not appear to be installed."
  fi

  if "$pybin" -c 'import tkinter' >/dev/null 2>&1; then
    log_ok "Tkinter present"
  else
    add_missing "python3-tk (Tkinter for the graphical interface)" \
                "sudo apt update && sudo apt install -y python3-tk" "python3-tk"
    log_warn "Tkinter is not available."
  fi
else
  log_info "Note: python3-venv and python3-tk will be verified again once Python 3.12 is installed."
fi

# ===========================================================================
# [6] Project files
# ===========================================================================
if [[ -f "$REQUIREMENTS" ]]; then
  log_ok "Project file found: ${REQUIREMENTS_FILE}"
else
  add_missing "project file '${REQUIREMENTS_FILE}' (expected in the project root)" \
              "re-extract the project ZIP so all files are present"
  log_warn "Could not find ${REQUIREMENTS_FILE} in ${SCRIPT_DIR}."
fi

# ===========================================================================
# [7] Decide: aggregate report, or proceed
# ===========================================================================
if (( ${#MISSING_LABELS[@]} )); then
  log_title "Setup is not ready yet — here is what's missing"
  log_info "Nothing has been changed. Install each item below, then run this script again."
  printf '\n'
  for i in "${!MISSING_LABELS[@]}"; do
    printf '  - %s\n' "${MISSING_LABELS[$i]}"
    printf '      %s\n' "${MISSING_FIXES[$i]}"
  done
  printf '\n'
  if [[ "$python_present" == 1 ]]; then
    log_info "Convenience one-liner for the missing host packages (Ubuntu/Pop!_OS):"
    log_info "    sudo apt update && sudo apt install -y ${WANTED_PKGS[*]}"
  else
    log_info "Install Python 3.12 with its usual companions, plus any missing host tools, then re-run:"
    log_info "    sudo apt update && sudo apt install -y python3.12 python3-venv python3-tk ${WANTED_PKGS[*]}"
  fi
  log_info "This tool does not use Conda, does not require git, and never installs host packages automatically."
  exit 1
fi

# ===========================================================================
# [8] Create or reuse the app-owned virtual environment
# ===========================================================================
log_title "Preparing the virtual environment"

# Reuse only when the existing venv is a working Python 3.12 with a working pip.
# Otherwise re-initialize the app-owned directory (we never delete user data;
# --clear acts only inside VENV_DIR).
if [[ -x "$VENV_PY" ]]; then
  existing_ver="$(py_report_version "$VENV_PY")"
  if python_is_312 "$existing_ver" && "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    log_ok "Reusing existing virtual environment: ${VENV_DIR} (Python ${existing_ver})"
  else
    log_warn "Existing venv is stale or has no pip (Python ${existing_ver:-unknown})."
    log_info "Re-initializing the app-owned virtual environment (only ${VENV_DIR} is touched)."
    if ! "$pybin" -m venv --clear "$VENV_DIR"; then
      log_error "Could not re-create the virtual environment."
      log_error "If this directory holds files you need, move them out and run this script again."
      exit 2
    fi
  fi
else
  log_info "Creating virtual environment: ${VENV_DIR}"
  if ! "$pybin" -m venv "$VENV_DIR"; then
    log_error "Could not create the virtual environment at ${VENV_DIR}."
    log_error "Check that you have write permission in ${SCRIPT_DIR}."
    exit 2
  fi
fi

# Authoritative check: a working pip is required to install dependencies.
if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
  log_error "The virtual environment was created but has no working 'pip'."
  log_error "This usually means the host package 'python3-venv' is missing."
  log_error "Install it, then run this script again:  sudo apt update && sudo apt install -y python3-venv"
  exit 1
fi
log_ok "Virtual environment ready: ${VENV_PY}"

# ===========================================================================
# [9] Install runtime Python dependencies (internet required, SRS 2.4)
# ===========================================================================
log_title "Installing Python dependencies (internet required)"
log_info "This installs only into ${VENV_NAME} — your host Python is untouched."

# pip self-upgrade is best-effort; a slightly stale pip is acceptable as long as
# the required packages install. The dependency install below is authoritative.
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 \
  || log_warn "pip self-upgrade skipped (not fatal); continuing with the dependency install."

if ! "$VENV_PY" -m pip install -r "$REQUIREMENTS"; then
  log_error "Could not install the Python dependencies from ${REQUIREMENTS_FILE}."
  log_error "This usually means there is no internet connection, or a package is unavailable."
  log_error "Check your connection, then run this script again."
  exit 1
fi
log_ok "Runtime dependencies installed."

# ===========================================================================
# [10] Done
# ===========================================================================
log_title "All done — you're set up"
log_info "Next steps:"
log_info "  1. Activate the environment:   source ${VENV_DIR}/bin/activate"
if [[ -f "${SCRIPT_DIR}/src/main.py" ]]; then
  log_info "  2. Start the application:       python src/main.py"
else
  log_info "  2. The application entry point (src/main.py) is available"
  log_info "     once the full project is in place."
fi
log_info "     (or run it without activating:  ${VENV_PY} src/main.py)"
log_info ""
log_info "Reminder: the app is read-only. It never writes to the drives it scans."

exit 0

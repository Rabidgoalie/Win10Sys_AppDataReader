#!/usr/bin/env bash
set -euo pipefail

VENV_NAME="Win10DRBPythonVenv"
REQUIRED_PYTHON="3.12.3"

echo "=== Windows 10 Disaster Recovery Bootstrap ==="
echo ""

# ----------------------------------------------------------------------------
# 1. Operating system check
# ----------------------------------------------------------------------------

if [ "$(uname -s)" != "Linux" ]; then
    echo ""
    echo "===================================================================="
    echo "ERROR: Unsupported operating system ($(uname -s))."
    echo ""
    echo "This application requires a Linux environment."
    echo ""
    echo "The recommended environment is an Ubuntu 24.04 Live Session."
    echo "Pop!_OS 24.04 and compatible Linux systems are also supported."
    echo "===================================================================="
    echo ""
    exit 1
fi

if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release

    case "${PRETTY_NAME:-}" in
        *Ubuntu\ 24.04*|*Pop!\_OS\ 24.04*)
            ;;
        *)
            echo "Notice: Detected Linux distribution: ${PRETTY_NAME:-unknown}"
            echo "This application is primarily designed for Ubuntu 24.04 Live Sessions."
            echo "Proceeding, but compatibility may vary."
            echo ""
            ;;
    esac
fi

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ----------------------------------------------------------------------------
# 2. Python check
# ----------------------------------------------------------------------------

if ! command_exists python3; then
    echo ""
    echo "ERROR: python3 is required but was not found."
    echo ""
    echo "This application requires Python ${REQUIRED_PYTHON} exactly."
    echo "Ubuntu 24.04 provides this version by default."
    echo ""
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:3] == (3, 12, 3) else 1)'; then
    DETECTED_PYTHON_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    echo ""
    echo "ERROR: Unsupported Python version: ${DETECTED_PYTHON_VERSION}"
    echo ""
    echo "This application requires Python ${REQUIRED_PYTHON} exactly."
    echo "Ubuntu 24.04 provides Python ${REQUIRED_PYTHON} by default."
    echo ""
    exit 1
fi

echo "Detected supported Python version: ${REQUIRED_PYTHON}"

if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Python virtual environment support is missing."
    echo ""
    echo "This application isolates its Python packages inside a local virtual"
    echo "environment to avoid polluting your host system."
    echo ""
    echo "Please install python3-venv manually, then re-run ./setup.sh."
    echo ""
    echo "On Ubuntu/Debian-based systems:"
    echo "  sudo apt-get update && sudo apt-get install -y python3-venv"
    echo ""
    exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Tkinter is required but was not found."
    echo ""
    echo "Tkinter provides this application's graphical interface."
    echo ""
    echo "Please install Tkinter manually, then re-run ./setup.sh."
    echo ""
    echo "On Ubuntu/Debian-based systems:"
    echo "  sudo apt-get update && sudo apt-get install -y python3-tk"
    echo ""
    exit 1
fi

# ----------------------------------------------------------------------------
# 3. Required system commands
# ----------------------------------------------------------------------------

MISSING_SYSTEM_COMMANDS=()

for required_command in sudo lsblk mount umount; do
    if ! command_exists "$required_command"; then
        MISSING_SYSTEM_COMMANDS+=("$required_command")
    fi
done

if [ "${#MISSING_SYSTEM_COMMANDS[@]}" -gt 0 ]; then
    echo ""
    echo "ERROR: Required system commands are missing:"
    echo ""
    for missing_command in "${MISSING_SYSTEM_COMMANDS[@]}"; do
        echo "  - $missing_command"
    done
    echo ""
    echo "These commands are required for safe drive discovery and read-only"
    echo "mount handling."
    echo ""
    echo "Please install them manually, then re-run ./setup.sh."
    echo ""
    exit 1
fi

# ----------------------------------------------------------------------------
# 4. ntfs-3g tool checks
# ----------------------------------------------------------------------------

find_tool() {
    local tool_name="$1"

    if command_exists "$tool_name"; then
        command -v "$tool_name"
        return 0
    fi

    local candidate_dir
    for candidate_dir in /sbin /usr/sbin /usr/local/sbin; do
        if [ -x "${candidate_dir}/${tool_name}" ]; then
            echo "${candidate_dir}/${tool_name}"
            return 0
        fi
    done

    return 1
}

MISSING_NTFS_TOOLS=()
PATH_ONLY_NTFS_TOOLS=()

for ntfs_tool in ntfsls ntfs-3g mount.ntfs-3g; do
    if tool_path="$(find_tool "$ntfs_tool")"; then
        if ! command_exists "$ntfs_tool"; then
            PATH_ONLY_NTFS_TOOLS+=("$tool_path")
        fi
    else
        MISSING_NTFS_TOOLS+=("$ntfs_tool")
    fi
done

if [ "${#MISSING_NTFS_TOOLS[@]}" -gt 0 ]; then
    echo ""
    echo "===================================================================="
    echo "CAUTION: Required ntfs-3g tooling was not detected."
    echo ""
    echo "This application uses ntfs-3g and ntfsls to keep your damaged"
    echo "Windows drives read-only and protected from accidental writes."
    echo ""
    echo "Missing tools:"
    for missing_tool in "${MISSING_NTFS_TOOLS[@]}"; do
        echo "  - $missing_tool"
    done
    echo ""
    echo "Please install ntfs-3g manually, then re-run ./setup.sh."
    echo ""
    echo "On Ubuntu/Debian-based systems:"
    echo "  sudo apt-get update && sudo apt-get install -y ntfs-3g"
    echo "===================================================================="
    echo ""
    exit 1
fi

if [ "${#PATH_ONLY_NTFS_TOOLS[@]}" -gt 0 ]; then
    PATH_DIRECTORIES=()

    for tool_path in "${PATH_ONLY_NTFS_TOOLS[@]}"; do
        tool_directory="$(dirname "$tool_path")"

        case " ${PATH_DIRECTORIES[*]:-} " in
            *" $tool_directory "*)
                ;;
            *)
                PATH_DIRECTORIES+=("$tool_directory")
                ;;
        esac
    done

    PATH_ADDITION=""
    for tool_directory in "${PATH_DIRECTORIES[@]}"; do
        if [ -z "$PATH_ADDITION" ]; then
            PATH_ADDITION="$tool_directory"
        else
            PATH_ADDITION="${PATH_ADDITION}:${tool_directory}"
        fi
    done

    echo ""
    echo "===================================================================="
    echo "CAUTION: Required ntfs-3g tools were found, but they are not in"
    echo "your current PATH."
    echo ""
    echo "These tools are critical because they allow the application to"
    echo "enumerate and mount NTFS drives in a safe, read-only manner."
    echo ""
    echo "If these tools are missing from PATH, the application cannot"
    echo "reliably protect your drives from accidental writes."
    echo ""
    echo "Required tools were found in these directories:"
    echo ""
    for tool_directory in "${PATH_DIRECTORIES[@]}"; do
        echo "  $tool_directory"
    done
    echo ""
    echo "Add the following line to your ~/.profile or ~/.bashrc file:"
    echo ""
    echo "  export PATH=\"${PATH_ADDITION}:\$PATH\""
    echo ""
    echo "Then log out and log back in, or run:"
    echo ""
    echo "  source ~/.profile"
    echo ""
    echo "After that, re-run ./setup.sh."
    echo "===================================================================="
    echo ""
    exit 1
fi

echo "Detected required ntfs-3g tooling."

# ----------------------------------------------------------------------------
# 5. Virtual environment setup
# ----------------------------------------------------------------------------

if [ -d "$VENV_NAME" ]; then
    echo "Reusing existing virtual environment: $VENV_NAME"
else
    echo "Creating isolated virtual environment: $VENV_NAME"
    python3 -m venv "$VENV_NAME"
fi

# shellcheck disable=SC1091
source "$VENV_NAME/bin/activate"

echo "Installing runtime Python dependencies into the virtual environment..."
echo "A working internet connection is required for this step."
echo ""

if ! python -m pip install --upgrade pip; then
    echo ""
    echo "ERROR: Failed to upgrade pip."
    echo ""
    echo "A working internet connection is required during setup."
    echo "Please check your network connection and re-run ./setup.sh."
    echo ""
    exit 1
fi

if ! python -m pip install -r requirements.txt; then
    echo ""
    echo "ERROR: Failed to install Python dependencies."
    echo ""
    echo "A working internet connection is required during setup."
    echo "Please check your network connection and re-run ./setup.sh."
    echo ""
    exit 1
fi

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "To activate the environment in future terminal sessions, run:"
echo ""
echo "  source ${VENV_NAME}/bin/activate"
echo ""
echo "To start the application, run:"
echo ""
echo "  python src/main.py"
echo ""
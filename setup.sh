#!/usr/bin/env bash
set -e

VENV_NAME="Win10DRBPythonVenv"

echo "=== Windows 10 Disaster Recovery Bootstrap (ADR-2) ==="

# Check for optional system utilities in Linux / Live USB context
if [ "$(uname)" = "Linux" ]; then
    if ! command -v ntfsls &> /dev/null && ! dpkg -s ntfs-3g &> /dev/null; then
        echo ""
        echo "===================================================================="
        echo "CAUTION: 'ntfs-3g' was not detected on this system."
        echo "Per our safety guarantees (ADR-1 & ADR-5), we use 'ntfs-3g' with strict"
        echo "read-only and dirty-bypass flags (-o ro,ro_dirty) to guarantee your"
        echo "damaged Windows partition remains 100% untouched and protected from"
        echo "accidental writes or metadata corruption."
        echo ""
        echo "To help you safely proceed without risking your data, please install it:"
        echo "  sudo apt-get update && sudo apt-get install -y ntfs-3g"
        echo "===================================================================="
        echo ""
        exit 1
    fi
    
    # Verify core mounting utilities required by ADR-5 mount manager
    if ! command -v mount &> /dev/null || ! command -v umount &> /dev/null; then
        echo "Error: Required system mounting utilities ('mount' / 'umount') are missing." >&2
        exit 1
    fi
else
    echo ""
    echo "===================================================================="
    echo "ERROR: Unsupported Operating System ($(uname))."
    echo "This application requires a Linux environment (specifically Ubuntu 24.04"
    echo "Live USB or compatible Linux installation) to safely parse raw NTFS"
    echo "partitions and offline Windows registry hives without kernel mounting."
    echo ""
    echo "Please create an Ubuntu 24.04 Live USB bootable drive, boot into it,"
    echo "and run this setup script from there."
    echo "===================================================================="
    echo ""
    exit 1
fi

# Check for Python 3.12+
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed." >&2
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Detected Python version: $PYTHON_VERSION"

# Check for python3-venv support (required for creating isolated environments)
if ! python3 -c "import venv" &> /dev/null; then
    echo ""
    echo "Notice: Python virtual environment support ('python3-venv') is required but not installed."
    echo "To protect potential dual-boot host systems, and maintain strict safety, this script will"
    echo "not automatically install system packages."
    echo ""
    echo "Please install it manually by running:"
    echo "  sudo apt-get update && sudo apt-get install -y python3-venv"
    echo ""
    echo "Once installed, please re-run './setup.sh'."
    exit 1
fi

# Set up local virtual environment (.venv)
if [ -d "$VENV_NAME" ]; then
    echo "Local virtual environment (.venv) already exists."
else
    echo "Creating isolated local virtual environment (.venv)..."
    python3 -m venv "$VENV_NAME"
fi

# Activate virtual environment and upgrade pip
echo "Activating virtual environment and installing application dependencies safely inside .venv..."
source "$VENV_NAME/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Bootstrap Complete ==="
echo "To activate your environment for future sessions, run:"
echo "  source $VENV_NAME/bin/activate"
echo ""
echo "To start the application, run:"
echo "  python src/main.py"
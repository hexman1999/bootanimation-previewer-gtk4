#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

abort() {
    echo "Error: $1" >&2
    exit 1
}

echo "Boot Animation Previewer Installer"
echo "=================================="
echo

if [[ $EUID -eq 0 ]]; then
    echo "Running as root — performing system-wide installation."
    MODE="global"
else
    echo "Choose installation mode:"
    echo "  1) Local (user only, no root required)"
    echo "  2) Global (system-wide, requires root via sudo)"
    read -rp "Enter choice [1/2]: " choice
    case "$choice" in
        1) MODE="local" ;;
        2) MODE="global" ;;
        *) abort "Invalid choice." ;;
    esac
fi

if [[ "$MODE" == "global" ]]; then
    if [[ $EUID -ne 0 ]]; then
        echo "Re-running with sudo for global installation..."
        exec sudo bash "$0" "$@"
    fi
    BIN_DIR="/usr/local/bin"
    ICON_DIR="/usr/local/share/icons/hicolor/scalable/apps"
    APP_DIR="/usr/local/share/applications"
    DESC_DIR="/usr/local/share/applications"
    mkdir -p "$BIN_DIR" "$ICON_DIR" "$DESC_DIR"
else
    BIN_DIR="${HOME}/.local/bin"
    ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
    APP_DIR="${HOME}/.local/share"
    DESC_DIR="${HOME}/.local/share/applications"
    mkdir -p "$BIN_DIR" "$ICON_DIR" "$DESC_DIR"
fi

echo
echo "Installing script..."
cp "$SCRIPT_DIR/previewer.py" "$BIN_DIR/bootanimation-previewer"
chmod 755 "$BIN_DIR/bootanimation-previewer"

echo "Installing icon..."
cp "$SCRIPT_DIR/bootanimation-previewer.svg" "$ICON_DIR/bootanimation-previewer.svg"

echo "Installing desktop entry..."
cat > "$DESC_DIR/org.antigravity.bootanimation_previewer.desktop" << EOF
[Desktop Entry]
Name=Boot Animation Previewer
Comment=Preview and export Android bootanimation.zip files
Exec=${BIN_DIR}/bootanimation-previewer
Icon=bootanimation-previewer
Terminal=false
Type=Application
Categories=Graphics;Utility;
StartupWMClass=org.antigravity.bootanimation_previewer
EOF

echo "Installing requirements..."
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null || true

echo "Updating desktop database..."
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESC_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache "$(dirname "$ICON_DIR")" -f -t 2>/dev/null || true
fi

echo
echo "Installation complete!"
echo
echo "You can now:"
echo "  - Run 'bootanimation-previewer' from the terminal"
echo "  - Launch from your application menu"
echo "  - Set as your boot animation previewer"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

abort() {
    echo "Error: $1" >&2
    exit 1
}

LOCAL_BIN="${HOME}/.local/bin"
LOCAL_ICON="${HOME}/.local/share/icons/hicolor/scalable/apps"
LOCAL_DESC="${HOME}/.local/share/applications"

GLOBAL_BIN="/usr/local/bin"
GLOBAL_ICON="/usr/local/share/icons/hicolor/scalable/apps"
GLOBAL_DESC="/usr/local/share/applications"

detect_installed() {
    local dirs=("$1" "$2" "$3")
    [[ -f "${dirs[0]}/bootanimation-previewer" || -f "${dirs[1]}/bootanimation-previewer.svg" || -f "${dirs[2]}/org.antigravity.bootanimation_previewer.desktop" ]]
}

do_install() {
    local bin="$1" icon="$2" desc="$3"

    echo "Installing script..."
    mkdir -p "$bin"
    cp "$SCRIPT_DIR/previewer.py" "$bin/bootanimation-previewer"
    chmod 755 "$bin/bootanimation-previewer"

    echo "Installing icon..."
    mkdir -p "$icon"
    cp "$SCRIPT_DIR/Resources/bootanimation-previewer.svg" "$icon/bootanimation-previewer.svg"

    echo "Installing desktop entry..."
    mkdir -p "$desc"
    cat > "$desc/org.antigravity.bootanimation_previewer.desktop" << EOF
[Desktop Entry]
Name=Boot Animation Previewer
Comment=Preview and export Android bootanimation.zip files
Exec=${bin}/bootanimation-previewer
Icon=bootanimation-previewer
Terminal=false
Type=Application
Categories=Graphics;Utility;
StartupWMClass=org.antigravity.bootanimation_previewer
EOF

    echo "Updating desktop database..."
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$desc" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache "$(dirname "$icon")" -f -t 2>/dev/null || true
    fi
}

do_uninstall() {
    local bin="$1" icon="$2" desc="$3" mode="$4"
    local removed=false

    if [[ "$mode" == "global" && $EUID -ne 0 ]]; then
        echo "Global uninstallation requires root privileges."
        exec sudo bash "$0" uninstall "$mode"
    fi

    if [[ -f "$bin/bootanimation-previewer" ]]; then
        rm "$bin/bootanimation-previewer"
        echo "  Removed: $bin/bootanimation-previewer"
        removed=true
    fi

    if [[ -f "$icon/bootanimation-previewer.svg" ]]; then
        rm "$icon/bootanimation-previewer.svg"
        echo "  Removed: $icon/bootanimation-previewer.svg"
        removed=true
    fi

    if [[ -f "$desc/org.antigravity.bootanimation_previewer.desktop" ]]; then
        rm "$desc/org.antigravity.bootanimation_previewer.desktop"
        echo "  Removed: $desc/org.antigravity.bootanimation_previewer.desktop"
        removed=true
    fi

    echo "Updating desktop database..."
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$desc" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache "$(dirname "$icon")" -f -t 2>/dev/null || true
    fi

    $removed && echo "Uninstallation complete." || echo "Nothing to uninstall in $mode."
}

echo "Boot Animation Previewer — Install / Uninstall"
echo "==============================================="
echo

if [[ ${1:-} == "uninstall" && -n ${2:-} ]]; then
    case "$2" in
        local)  do_uninstall "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC" "local" ;;
        global) do_uninstall "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC" "global" ;;
    esac
    exit 0
fi

echo "Select action:"
echo "  1) Install"
echo "  2) Uninstall"
read -rp "Enter choice [1/2]: " action
echo

case "$action" in
    1)
        if [[ $EUID -eq 0 ]]; then
            echo "Installing system-wide..."
            do_install "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC"
            pip install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null || true
        else
            echo "Choose installation mode:"
            echo "  1) Local (user only, no root)"
            echo "  2) Global (system-wide, requires sudo)"
            read -rp "Enter choice [1/2]: " choice
            case "$choice" in
                1)
                    do_install "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC"
                    pip install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null || true
                    ;;
                2)
                    echo "Re-running with sudo for global installation..."
                    exec sudo bash "$0" "install" "global"
                    ;;
                *) abort "Invalid choice." ;;
            esac
        fi
        echo
        echo "Installation complete!"
        echo
        echo "You can now:"
        echo "  - Run 'bootanimation-previewer' from the terminal"
        echo "  - Launch from your application menu"
        ;;
    2)
        echo "Detecting installed copies..."
        echo

        local_found=false
        global_found=false

        if detect_installed "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC"; then
            echo "  [1] Local installation found (${HOME}/.local)"
            local_found=true
        fi
        if detect_installed "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC"; then
            echo "  [2] Global installation found (/usr/local)"
            global_found=true
        fi

        if ! $local_found && ! $global_found; then
            echo "No installation found."
            exit 0
        fi

        echo
        if $local_found && $global_found; then
            echo "Select which to uninstall:"
            echo "  1) Local only"
            echo "  2) Global only"
            echo "  3) Both"
            read -rp "Enter choice [1/2/3]: " choice
            case "$choice" in
                1) do_uninstall "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC" "local" ;;
                2) do_uninstall "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC" "global" ;;
                3)
                    do_uninstall "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC" "local"
                    do_uninstall "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC" "global"
                    ;;
                *) abort "Invalid choice." ;;
            esac
        elif $local_found; then
            echo "Uninstalling local installation..."
            do_uninstall "$LOCAL_BIN" "$LOCAL_ICON" "$LOCAL_DESC" "local"
        else
            echo "Uninstalling global installation..."
            do_uninstall "$GLOBAL_BIN" "$GLOBAL_ICON" "$GLOBAL_DESC" "global"
        fi
        ;;
    *)
        abort "Invalid choice."
        ;;
esac

#!/usr/bin/env bash
# Browseye — setup script
# Installs dependencies, creates symlinks, and prints instructions

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FF_CONTROL="$PROJECT_DIR/client/ff_control.py"
SERVER="$PROJECT_DIR/server/controller_server.py"
EXTENSION="$PROJECT_DIR/extension"
BIN_DIR="$HOME/.local/bin"
SYMLINK="$BIN_DIR/ff_control"

echo "=== Browseye Setup ==="
echo ""

# 1. Install Python dependencies
echo "[1/4] Installing Python dependencies..."
pip3 install websockets --quiet --break-system-packages 2>/dev/null || \
  pip3 install websockets --quiet --user 2>/dev/null || \
  pip3 install websockets --quiet 2>/dev/null || {
    echo "Could not install websockets. Try: pip install websockets"
    exit 1
  }
echo "  ✓ websockets installed"

# 2. Create bin directory and symlink
echo "[2/4] Installing CLI client..."
mkdir -p "$BIN_DIR"
chmod +x "$FF_CONTROL"
if [ -f "$SYMLINK" ]; then
  rm -f "$SYMLINK"
fi
ln -sf "$FF_CONTROL" "$SYMLINK"
echo "  ✓ Symlinked ff_control -> $SYMLINK"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "  ⚠  $BIN_DIR is not in your PATH"
  echo "     Add this to your ~/.config/fish/config.fish:"
  echo "     set -U fish_user_paths \$fish_user_paths $BIN_DIR"
fi

# 3. Create server autostart (user systemd service)
echo "[3/4] Setting up server autostart (systemd --user)..."
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/browseye.service" << EOSERVICE
[Unit]
Description=Browseye WebSocket Server
After=network.target

[Service]
Type=simple
ExecStart=$SERVER
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOSERVICE

chmod 644 "$SERVICE_DIR/browseye.service"
systemctl --user daemon-reload 2>/dev/null || true
echo "  ✓ Service file created at $SERVICE_DIR/browseye.service"
echo "  To enable autostart:  systemctl --user enable browseye"
echo "  To start now:         systemctl --user start browseye"

# 4. Extension install instructions
echo "[4/4] Firefox extension"
echo "  Extension source: $EXTENSION"
echo ""
echo "  To install in Firefox:"
echo "  1. Open Firefox and go to about:debugging"
echo "  2. Click 'This Firefox'"
echo "  3. Click 'Load Temporary Add-on...'"
echo "  4. Select $EXTENSION/manifest.json"
echo ""
echo "  For permanent installation:"
echo "  1. Go to about:config"
echo "  2. Set xpinstall.signatures.required to false"
echo "  3. Zip the extension:"
echo "     cd $EXTENSION && zip -r ../browseye.zip *"
echo "  4. Open about:addons → Gear icon → Install Add-on From File"
echo ""

# Start server
echo "[optional] Starting server now..."
systemctl --user start browseye 2>/dev/null || {
  echo "  Starting server directly..."
  python3 "$SERVER" --daemon 2>/dev/null && echo "  ✓ Server started" || echo "  Could not start server"
}

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick test:"
echo "  ff_control --status"
echo "  ff_control ping"
echo "  ff_control tab_list"
echo "  ff_control -i              # Interactive mode"

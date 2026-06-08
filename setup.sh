1|#!/usr/bin/env bash
2|# Browseye — setup script
3|# Installs dependencies, creates symlinks, and prints instructions
4|
5|set -euo pipefail
6|
7|PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
8|FF_CONTROL="$PROJECT_DIR/client/ff_control.py"
9|SERVER="$PROJECT_DIR/server/controller_server.py"
10|EXTENSION="$PROJECT_DIR/extension"
11|BIN_DIR="$HOME/.local/bin"
12|SYMLINK="$BIN_DIR/ff_control"
13|
14|echo "=== Browseye Setup ==="
15|echo ""
16|
17|# 1. Install Python dependencies
18|echo "[1/4] Installing Python dependencies..."
19|pip3 install websockets --quiet --break-system-packages 2>/dev/null || \
20|  pip3 install websockets --quiet --user 2>/dev/null || \
21|  pip3 install websockets --quiet 2>/dev/null || {
22|    echo "Could not install websockets. Try: pip install websockets"
23|    exit 1
24|  }
25|echo "  ✓ websockets installed"
26|
27|# 2. Create bin directory and symlink
28|echo "[2/4] Installing CLI client..."
29|mkdir -p "$BIN_DIR"
30|chmod +x "$FF_CONTROL"
31|if [ -f "$SYMLINK" ]; then
32|  rm -f "$SYMLINK"
33|fi
34|ln -sf "$FF_CONTROL" "$SYMLINK"
35|echo "  ✓ Symlinked ff_control -> $SYMLINK"
36|
37|# Check PATH
38|if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
39|  echo "  ⚠  $BIN_DIR is not in your PATH"
40|  echo "     Add this to your ~/.config/fish/config.fish:"
41|  echo "     set -U fish_user_paths \$fish_user_paths $BIN_DIR"
42|fi
43|
44|# 3. Create server autostart (user systemd service)
45|echo "[3/4] Setting up server autostart (systemd --user)..."
46|SERVICE_DIR="$HOME/.config/systemd/user"
47|mkdir -p "$SERVICE_DIR"
48|
49|cat > "$SERVICE_DIR/browseye.service" << EOSERVICE
50|[Unit]
51|Description=Browseye WebSocket Server
52|After=network.target
53|
54|[Service]
55|Type=simple
56|ExecStart=$SERVER
57|Restart=on-failure
58|RestartSec=3
59|
60|[Install]
61|WantedBy=default.target
62|EOSERVICE
63|
64|chmod 644 "$SERVICE_DIR/browseye.service"
65|systemctl --user daemon-reload 2>/dev/null || true
66|echo "  ✓ Service file created at $SERVICE_DIR/browseye.service"
67|echo "  To enable autostart:  systemctl --user enable browseye"
68|echo "  To start now:         systemctl --user start browseye"
69|
70|# 4. Extension install instructions
71|echo "[4/4] Firefox extension"
72|echo "  Extension source: $EXTENSION"
73|echo ""
74|echo "  To install in Firefox:"
75|echo "  1. Open Firefox and go to about:debugging"
76|echo "  2. Click 'This Firefox'"
77|echo "  3. Click 'Load Temporary Add-on...'"
78|echo "  4. Select $EXTENSION/manifest.json"
79|echo ""
80|echo "  For permanent installation:"
81|echo "  1. Go to about:config"
82|echo "  2. Set xpinstall.signatures.required to false"
83|echo "  3. Zip the extension:"
84|echo "     cd $EXTENSION && zip -r ../browseye.zip *"
85|echo "  4. Open about:addons → Gear icon → Install Add-on From File"
86|echo ""
87|
88|# Start server
89|echo "[optional] Starting server now..."
90|systemctl --user start browseye 2>/dev/null || {
91|  echo "  Starting server directly..."
92|  python3 "$SERVER" --daemon 2>/dev/null && echo "  ✓ Server started" || echo "  Could not start server"
93|}
94|
95|echo ""
96|echo "=== Setup Complete ==="
97|echo ""
98|echo "Quick test:"
99|echo "  ff_control --status"
100|echo "  ff_control ping"
101|echo "  ff_control tab_list"
102|echo "  ff_control -i              # Interactive mode"
103|
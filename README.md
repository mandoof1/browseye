# Browseye

![Made with JavaScript](https://img.shields.io/badge/Made%20with-JavaScript-F7DF1E?logo=javascript)
![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python)
![Firefox Extension](https://img.shields.io/badge/Firefox-Extension-FF7139?logo=firefox)

Browseye is a full browser control system for Firefox. It gives you programmatic access to every browser capability — tabs, windows, DOM, cookies, history, downloads, network requests, storage, bookmarks, clipboard, and more — all through a WebSocket interface from your terminal or scripts.

The project consists of three components:

- **Firefox Extension** — connects to a local WebSocket server and executes browser API commands
- **Control Server** — Python asyncio server that bridges commands between the extension and CLI clients
- **CLI Client** — command-line tool for sending commands interactively or from scripts

## Architecture

```
┌─────────────┐     ws://:8765     ┌──────────────────┐
│  Firefox     │◄──────────────────│  Browseye        │
│  Extension   │   commands/       │  Server (Python) │
│  (agent)     │   responses       │  :8765 + :8766   │
└─────────────┘                    └────────┬─────────┘
                                            │ ws://:8766
                                    ┌───────▼─────────┐
                                    │  CLI Client     │
                                    │  ff_control     │
                                    └─────────────────┘
```

The extension registers as the **agent** on port 8765. CLI tools and scripts connect as **clients** on port 8766. The server relays commands from clients to the extension and returns responses.

## Features

### Tab & Window Management
Open, close, switch between, duplicate, move, discard, mute, and reload tabs. Create and manage multiple windows including incognito windows.

### Page Interaction
Execute arbitrary JavaScript, read and modify DOM, click elements, fill forms, select dropdowns, scroll, wait for elements, extract links and form structures.

### Data Extraction
Get page HTML, text content, URLs, titles. Take screenshots. Extract cookies, localStorage, sessionStorage. Read clipboard contents.

### Network Monitoring
Capture HTTP requests and responses as they happen. Block URLs matching patterns. Inspect request/response headers and bodies.

### History & Downloads
Search browsing history, delete entries. Trigger downloads, list recent downloads, open or delete downloaded files.

### Bookmarks & Sessions
List, create, and remove bookmarks. View recently closed tabs and restore them.

### Storage & Clipboard
Read and write extension storage, page storage, and system clipboard. Show desktop notifications.

## Quick Start

### Prerequisites

- Python 3.8+
- Firefox 91+

### Installation

```bash
# Install the Python dependency
pip install websockets

# Clone the repository
git clone https://github.com/mandoof1/browseye.git
cd browseye

# Run the setup script
chmod +x setup.sh
./setup.sh
```

### Load the Extension

1. Open Firefox and navigate to `about:debugging`
2. Click **This Firefox** → **Load Temporary Add-on**
3. Select `browseye/extension/manifest.json`

The extension will connect to the server automatically. You'll see it in the toolbar with a connection status indicator.

### Usage

```bash
# Check the server is running
ff_control ping

# List all open tabs
ff_control tab_list

# Navigate to a URL
ff_control navigate '{"url": "https://example.com"}'

# Execute JavaScript on the current page
ff_control page_eval '{"code": "document.title"}'

# Take a screenshot
ff_control page_screenshot

# Get cookies for the current site
ff_control cookies_get

# Interactive mode
ff_control -i
```

## Command Reference

### Tab Management

| Command | Parameters | Description |
|---------|-----------|-------------|
| `tab_list` | — | List all open tabs |
| `tab_get` | `tabId` | Get tab details |
| `tab_create` | `url`, `active` | Create a new tab |
| `tab_close` | `tabId` / `tabIds[]` | Close one or more tabs |
| `tab_activate` | `tabId` | Switch to a tab |
| `tab_update` | `tabId`, `url`, `active` | Modify a tab |
| `tab_reload` | `tabId`, `bypassCache` | Reload a tab |
| `tab_duplicate` | `tabId` | Duplicate a tab |
| `tab_move` | `tabId`, `index`, `windowId` | Move a tab to a new position |
| `tab_discard` | `tabId` | Unload a tab from memory |
| `tab_mute` / `tab_unmute` | `tabId` | Mute or unmute a tab |

### Window Management

| Command | Parameters | Description |
|---------|-----------|-------------|
| `window_list` | — | List all open windows |
| `window_create` | `url`, `type`, `state`, `incognito` | Create a new window |
| `window_close` | `windowId` | Close a window |

### Page / DOM

| Command | Parameters | Description |
|---------|-----------|-------------|
| `page_eval` | `code` | Execute JavaScript in page context |
| `page_get_html` | `tabId` | Get page HTML |
| `page_get_text` | `tabId` | Get page text content |
| `page_get_title` | `tabId` | Get page title |
| `page_get_url` | `tabId` | Get page URL |
| `page_screenshot` | `format`, `quality` | Take a screenshot |
| `page_click` | `selector` | Click a DOM element |
| `page_fill` | `selector`, `value` | Fill a form field |
| `page_select` | `selector`, `value` | Select a dropdown option |
| `page_scroll` | `x`, `y`, `smooth` | Scroll the page |
| `page_scroll_to` | `x`, `y`, `smooth` | Scroll to a specific position |
| `page_wait` | `timeout` / `selector` | Wait for time or element |
| `page_get_links` | `tabId` | Extract all links from the page |
| `page_get_forms` | `tabId` | Extract form structure |
| `page_get_attributes` | `selector` | Get element attributes |

### Cookies

| Command | Parameters | Description |
|---------|-----------|-------------|
| `cookies_get` | `url`, `domain`, `name` | Get cookies |
| `cookies_set` | `name`, `value`, `domain`, `path`, `secure`, `httpOnly` | Set a cookie |
| `cookies_remove` | `name`, `url` | Remove a cookie |
| `cookies_clear` | — | Clear all cookies |

### History

| Command | Parameters | Description |
|---------|-----------|-------------|
| `history_search` | `text`, `maxResults`, `startTime`, `endTime` | Search browsing history |
| `history_delete_url` | `url` | Remove a URL from history |
| `history_delete_range` | `startTime`, `endTime` | Remove a time range |
| `history_clear` | — | Clear all browsing history |

### Downloads

| Command | Parameters | Description |
|---------|-----------|-------------|
| `downloads_download` | `url`, `filename`, `conflictAction` | Download a file |
| `downloads_list` | — | List recent downloads |
| `downloads_open` | `downloadId` | Open a downloaded file |
| `downloads_remove_file` | `downloadId` | Delete a downloaded file |

### Storage

| Command | Parameters | Description |
|---------|-----------|-------------|
| `storage_get_local` | `key` | Get extension storage value |
| `storage_set_local` | `data` | Set extension storage values |
| `storage_clear_local` | — | Clear extension storage |
| `storage_get_page` | `tabId` | Get page localStorage/sessionStorage |

### Network Interception

| Command | Parameters | Description |
|---------|-----------|-------------|
| `network_start` | — | Start capturing network requests |
| `network_stop` | — | Stop capturing |
| `network_get` | `keep` | Get captured requests |
| `network_clear` | — | Clear captured request buffer |
| `network_block` | `pattern` | Block URLs matching a pattern |

### Bookmarks

| Command | Parameters | Description |
|---------|-----------|-------------|
| `bookmarks_list` | — | List all bookmarks |
| `bookmarks_create` | `title`, `url`, `parentId` | Create a bookmark |
| `bookmarks_remove` | `id` | Remove a bookmark |

### Other

| Command | Parameters | Description |
|---------|-----------|-------------|
| `sessions_list` | `maxResults` | List recently closed tabs |
| `sessions_restore` | `sessionId` | Restore a closed tab |
| `clipboard_read` | `tabId` | Read clipboard content |
| `clipboard_write` | `text` | Write to clipboard |
| `notify` | `title`, `message` | Show a desktop notification |
| `browser_info` | — | Get Firefox version and platform info |
| `tab_insert_css` | `code`, `file`, `allFrames` | Inject CSS into a page |
| `ping` | — | Health check |

## Permanent Installation

To install the extension permanently (not just temporarily):

1. Open Firefox `about:config` and set `xpinstall.signatures.required` to `false`
2. Build the extension package:
   ```bash
   cd browseye/extension
   zip -r ../browseye.zip *
   ```
3. Open `about:addons` → click the gear icon → **Install Add-on From File**
4. Select `browseye.zip`

## Server Management

The server can be managed as a systemd user service:

```bash
# Start the server
systemctl --user start browseye

# Enable autostart on login
systemctl --user enable browseye

# Check status
systemctl --user status browseye

# View logs
journalctl --user -u browseye -f
```

## License

This project is for educational and authorized security testing purposes only.

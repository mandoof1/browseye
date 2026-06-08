#!/usr/bin/env python3
"""
Browseye — CLI client

Connects to the Browseye server and sends commands to the Firefox extension.

Usage:
    ff_control <command> [params_json]
    ff_control --json <command> [params_json]
    ff_control --interactive
    ff_control --status

Examples:
    ff_control tab_list
    ff_control tab_get '{"tabId": 3}'
    ff_control navigate '{"url": "https://example.com"}'
    ff_control page_eval '{"code": "document.title"}'
    ff_control cookies_get
    ff_control page_screenshot
    ff_control -i
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

HOST = '127.0.0.1'
CLIENT_PORT = 8766  # Server-side client port = PORT + 1

try:
    import websockets
    from websockets.asyncio.client import connect as ws_connect
except ImportError:
    print("Missing 'websockets' package. Install with: pip install websockets", file=sys.stderr)
    sys.exit(1)


def pretty_print(data, json_mode: bool):
    """Format the response for output."""
    if json_mode:
        print(json.dumps(data, indent=2, default=str))
        return

    if isinstance(data, dict):
        # If it has 'data' key, unwrap for cleaner display
        if 'data' in data:
            inner = data['data']
            if 'error' in data and data['error']:
                print(f"Error: {data['error']}", file=sys.stderr)
                return
            pretty_print(inner, False)
            return

        # Special formatting for certain result types
        if 'success' in data and data.get('data'):
            pretty_print(data['data'], False)
            return

        # For simple key-value results
        if len(data) <= 6:
            max_key = max(len(k) for k in data.keys()) if data else 0
            for k, v in data.items():
                v_str = str(v)
                if len(v_str) > 120:
                    v_str = v_str[:117] + '...'
                print(f"  {k:<{max_key}}  {v_str}")
        else:
            print(json.dumps(data, indent=2, default=str))

    elif isinstance(data, list):
        if len(data) == 0:
            print("(empty)")
        elif all(isinstance(i, dict) for i in data):
            # Table format for list of dicts
            if len(data[0]) <= 6:
                keys = list(data[0].keys())
                col_widths = {}
                for k in keys:
                    col_widths[k] = max(
                        len(k),
                        max((len(str(item.get(k, ''))) for item in data), default=0)
                    )
                    col_widths[k] = min(col_widths[k], 60)

                # Header
                header = '  '.join(k.ljust(col_widths[k]) for k in keys)
                print(header)
                print('  '.join('─' * col_widths[k] for k in keys))
                for item in data:
                    row = '  '.join(
                        str(item.get(k, '')).ljust(col_widths[k])[:col_widths[k]]
                        for k in keys
                    )
                    print(row)
            else:
                for item in data:
                    print(json.dumps(item, indent=2, default=str))
                    print()
        else:
            for item in data:
                print(item)

    elif isinstance(data, str):
        print(data)
    else:
        print(data)


async def send_command(command: str, params: dict = None, timeout: float = 30.0) -> dict:
    """Connect to server, send command, return response."""
    uri = f"ws://{HOST}:{CLIENT_PORT}"

    try:
        async with ws_connect(uri, open_timeout=5) as ws:
            cmd_id = str(uuid.uuid4())[:8]
            msg = json.dumps({
                'type': 'command',
                'id': cmd_id,
                'command': command,
                'params': params or {},
                'timeout': timeout
            })

            await ws.send(msg)

            # Wait for response with overall timeout
            response = await asyncio.wait_for(ws.recv(), timeout=timeout + 5)
            data = json.loads(response)

            if data.get('type') == 'response':
                return {
                    'success': data.get('success', False),
                    'data': data.get('data'),
                    'error': data.get('error'),
                    'command': command,
                    'id': cmd_id
                }
            else:
                return {'success': False, 'error': f"Unexpected response type: {data.get('type')}"}

    except asyncio.TimeoutError:
        return {'success': False, 'error': f"Command '{command}' timed out"}
    except websockets.exceptions.WebSocketException as e:
        return {'success': False, 'error': f"Connection failed: {e}"}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def check_status() -> dict:
    """Ping the server for status."""
    uri = f"ws://{HOST}:{CLIENT_PORT}"
    try:
        async with ws_connect(uri, open_timeout=3) as ws:
            await ws.send(json.dumps({'type': 'status'}))
            response = await asyncio.wait_for(ws.recv(), timeout=3)
            return json.loads(response)
    except Exception as e:
        return {'error': str(e), 'agent_connected': False}


def ensure_server():
    """Start the server if it's not running."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, 8765))
        sock.close()
        return True  # Server is running
    except ConnectionRefusedError:
        pass
    finally:
        sock.close()

    # Try to start it
    server_script = Path(__file__).parent / 'controller_server.py'
    if not server_script.exists():
        # Check in the project dir too
        alt_path = Path.home() / 'firefox-controller' / 'server' / 'controller_server.py'
        if alt_path.exists():
            server_script = alt_path
        else:
            return False

    print("Starting Browseye server...", file=sys.stderr)
    try:
        subprocess.Popen(
            [sys.executable, str(server_script), '--daemon'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        # Wait for it to be ready
        import time
        for _ in range(10):
            time.sleep(0.5)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect((HOST, 8765))
                sock.close()
                print("Server started.", file=sys.stderr)
                return True
            except:
                pass
        print("Failed to start server.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Failed to start server: {e}", file=sys.stderr)
        return False


async def interactive_mode():
    """REPL mode for interactive use."""
    print("Browseye Interactive Mode")
    print("Type 'help' for commands, 'quit' to exit.")
    print()

    if not ensure_server():
        print("Cannot connect to server. Is it running?", file=sys.stderr)
        return

    history = []

    while True:
        try:
            cmd_line = input("ffc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd_line:
            continue

        if cmd_line == 'quit' or cmd_line == 'exit':
            break

        if cmd_line == 'help':
            print("Commands:")
            print("  <command> [params_json]    Execute a command")
            print("  status                     Check connection status")
            print("  history                    Show command history")
            print("  clear                      Clear screen")
            print("  help                       This help")
            print("  quit / exit                Exit")
            print()
            print("Available commands (send to extension):")
            print("  tab_list, tab_get, tab_create, tab_close, tab_activate")
            print("  navigate, page_eval, page_get_html, page_get_text")
            print("  page_screenshot, page_click, page_fill")
            print("  cookies_get, cookies_set, cookies_remove")
            print("  network_start, network_stop, network_get")
            print("  downloads_download, history_search")
            print("  window_list, window_create, page_get_forms, page_get_links")
            print("  storage_get_local, storage_get_page")
            print("  bookmarks_list, sessions_list, browser_info")
            print("  clipboard_read, clipboard_write, notify")
            print("  tab_execute_script, tab_insert_css")
            print("  ping, get_info")
            continue

        if cmd_line == 'status':
            status = await check_status()
            if 'error' in status:
                print(f"Server: Error ({status['error']})")
            else:
                print(f"Server: Running")
                print(f"Agent connected: {status.get('agent_connected', False)}")
                print(f"Pending commands: {status.get('pending_commands', 0)}")
            continue

        if cmd_line == 'history':
            for i, h in enumerate(history[-20:], 1):
                print(f"  {i:3d}.  {h}")
            continue

        if cmd_line == 'clear':
            subprocess.run(['clear'] if os.name == 'posix' else ['cls'])
            continue

        # Parse command and optional params
        parts = cmd_line.split(maxsplit=1)
        command = parts[0]
        params = {}
        if len(parts) > 1:
            try:
                params = json.loads(parts[1])
            except json.JSONDecodeError:
                print(f"Invalid JSON params: {parts[1]}")
                continue

        history.append(cmd_line)
        result = await send_command(command, params)
        print()
        if result.get('success'):
            pretty_print(result.get('data'), False)
        else:
            print(f"Error: {result.get('error', 'unknown')}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Browseye — control Firefox from the command line',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s tab_list
  %(prog)s navigate '{"url": "https://example.com"}'
  %(prog)s page_eval '{"code": "document.title"}'
  %(prog)s page_screenshot
  %(prog)s cookies_get
  %(prog)s --json tab_get '{"tabId": 3}'
        """
    )
    parser.add_argument('command', nargs='?', help='Command to execute')
    parser.add_argument('params', nargs='?', default='{}', help='JSON parameters')
    parser.add_argument('--json', '-j', action='store_true', help='Output raw JSON')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive REPL mode')
    parser.add_argument('--status', '-s', action='store_true', help='Check server status')
    parser.add_argument('--timeout', '-t', type=int, default=30, help='Command timeout in seconds')
    parser.add_argument('--no-autostart', action='store_true', help="Don't auto-start the server")

    args = parser.parse_args()

    if args.status:
        status = asyncio.run(check_status())
        if 'error' in status:
            print(f"Server: OFFLINE ({status['error']})")
        else:
            print(f"Server: ONLINE")
            print(f"Agent connected: {status.get('agent_connected', False)}")
            print(f"Pending commands: {status.get('pending_commands', 0)}")
        return

    if args.interactive:
        asyncio.run(interactive_mode())
        return

    if not args.command:
        if args.params != '{}':
            print("Error: params provided without command", file=sys.stderr)
            sys.exit(1)
        parser.print_help()
        sys.exit(1)

    if not args.no_autostart:
        ensure_server()

    # Parse params
    params = {}
    if args.params and args.params != '{}':
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            print(f"Error: invalid JSON params: {args.params}", file=sys.stderr)
            sys.exit(1)

    # Execute
    result = asyncio.run(send_command(args.command, params, timeout=args.timeout))

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get('success'):
            pretty_print(result.get('data'), False)
        else:
            print(f"Error: {result.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()

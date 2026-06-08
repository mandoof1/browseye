1|#!/usr/bin/env python3
2|"""
3|Browseye — CLI client
4|
5|Connects to the Browseye server and sends commands to the Firefox extension.
6|
7|Usage:
8|    ff_control <command> [params_json]
9|    ff_control --json <command> [params_json]
10|    ff_control --interactive
11|    ff_control --status
12|
13|Examples:
14|    ff_control tab_list
15|    ff_control tab_get '{"tabId": 3}'
16|    ff_control navigate '{"url": "https://example.com"}'
17|    ff_control page_eval '{"code": "document.title"}'
18|    ff_control cookies_get
19|    ff_control page_screenshot
20|    ff_control -i
21|"""
22|
23|import argparse
24|import asyncio
25|import json
26|import os
27|import subprocess
28|import sys
29|import uuid
30|from pathlib import Path
31|
32|HOST = '127.0.0.1'
33|CLIENT_PORT = 8766  # Server-side client port = PORT + 1
34|
35|try:
36|    import websockets
37|    from websockets.asyncio.client import connect as ws_connect
38|except ImportError:
39|    print("Missing 'websockets' package. Install with: pip install websockets", file=sys.stderr)
40|    sys.exit(1)
41|
42|
43|def pretty_print(data, json_mode: bool):
44|    """Format the response for output."""
45|    if json_mode:
46|        print(json.dumps(data, indent=2, default=str))
47|        return
48|
49|    if isinstance(data, dict):
50|        # If it has 'data' key, unwrap for cleaner display
51|        if 'data' in data:
52|            inner = data['data']
53|            if 'error' in data and data['error']:
54|                print(f"Error: {data['error']}", file=sys.stderr)
55|                return
56|            pretty_print(inner, False)
57|            return
58|
59|        # Special formatting for certain result types
60|        if 'success' in data and data.get('data'):
61|            pretty_print(data['data'], False)
62|            return
63|
64|        # For simple key-value results
65|        if len(data) <= 6:
66|            max_key = max(len(k) for k in data.keys()) if data else 0
67|            for k, v in data.items():
68|                v_str = str(v)
69|                if len(v_str) > 120:
70|                    v_str = v_str[:117] + '...'
71|                print(f"  {k:<{max_key}}  {v_str}")
72|        else:
73|            print(json.dumps(data, indent=2, default=str))
74|
75|    elif isinstance(data, list):
76|        if len(data) == 0:
77|            print("(empty)")
78|        elif all(isinstance(i, dict) for i in data):
79|            # Table format for list of dicts
80|            if len(data[0]) <= 6:
81|                keys = list(data[0].keys())
82|                col_widths = {}
83|                for k in keys:
84|                    col_widths[k] = max(
85|                        len(k),
86|                        max((len(str(item.get(k, ''))) for item in data), default=0)
87|                    )
88|                    col_widths[k] = min(col_widths[k], 60)
89|
90|                # Header
91|                header = '  '.join(k.ljust(col_widths[k]) for k in keys)
92|                print(header)
93|                print('  '.join('─' * col_widths[k] for k in keys))
94|                for item in data:
95|                    row = '  '.join(
96|                        str(item.get(k, '')).ljust(col_widths[k])[:col_widths[k]]
97|                        for k in keys
98|                    )
99|                    print(row)
100|            else:
101|                for item in data:
102|                    print(json.dumps(item, indent=2, default=str))
103|                    print()
104|        else:
105|            for item in data:
106|                print(item)
107|
108|    elif isinstance(data, str):
109|        print(data)
110|    else:
111|        print(data)
112|
113|
114|async def send_command(command: str, params: dict = None, timeout: float = 30.0) -> dict:
115|    """Connect to server, send command, return response."""
116|    uri = f"ws://{HOST}:{CLIENT_PORT}"
117|
118|    try:
119|        async with ws_connect(uri, open_timeout=5) as ws:
120|            cmd_id = str(uuid.uuid4())[:8]
121|            msg = json.dumps({
122|                'type': 'command',
123|                'id': cmd_id,
124|                'command': command,
125|                'params': params or {},
126|                'timeout': timeout
127|            })
128|
129|            await ws.send(msg)
130|
131|            # Wait for response with overall timeout
132|            response = await asyncio.wait_for(ws.recv(), timeout=timeout + 5)
133|            data = json.loads(response)
134|
135|            if data.get('type') == 'response':
136|                return {
137|                    'success': data.get('success', False),
138|                    'data': data.get('data'),
139|                    'error': data.get('error'),
140|                    'command': command,
141|                    'id': cmd_id
142|                }
143|            else:
144|                return {'success': False, 'error': f"Unexpected response type: {data.get('type')}"}
145|
146|    except asyncio.TimeoutError:
147|        return {'success': False, 'error': f"Command '{command}' timed out"}
148|    except websockets.exceptions.WebSocketException as e:
149|        return {'success': False, 'error': f"Connection failed: {e}"}
150|    except Exception as e:
151|        return {'success': False, 'error': str(e)}
152|
153|
154|async def check_status() -> dict:
155|    """Ping the server for status."""
156|    uri = f"ws://{HOST}:{CLIENT_PORT}"
157|    try:
158|        async with ws_connect(uri, open_timeout=3) as ws:
159|            await ws.send(json.dumps({'type': 'status'}))
160|            response = await asyncio.wait_for(ws.recv(), timeout=3)
161|            return json.loads(response)
162|    except Exception as e:
163|        return {'error': str(e), 'agent_connected': False}
164|
165|
166|def ensure_server():
167|    """Start the server if it's not running."""
168|    import socket
169|    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
170|    try:
171|        sock.connect((HOST, 8765))
172|        sock.close()
173|        return True  # Server is running
174|    except ConnectionRefusedError:
175|        pass
176|    finally:
177|        sock.close()
178|
179|    # Try to start it
180|    server_script = Path(__file__).parent / 'controller_server.py'
181|    if not server_script.exists():
182|        # Check in the project dir too
183|        alt_path = Path.home() / 'firefox-controller' / 'server' / 'controller_server.py'
184|        if alt_path.exists():
185|            server_script = alt_path
186|        else:
187|            return False
188|
189|    print("Starting Browseye server...", file=sys.stderr)
190|    try:
191|        subprocess.Popen(
192|            [sys.executable, str(server_script), '--daemon'],
193|            stdout=subprocess.DEVNULL,
194|            stderr=subprocess.DEVNULL,
195|            start_new_session=True
196|        )
197|        # Wait for it to be ready
198|        import time
199|        for _ in range(10):
200|            time.sleep(0.5)
201|            try:
202|                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
203|                sock.settimeout(1)
204|                sock.connect((HOST, 8765))
205|                sock.close()
206|                print("Server started.", file=sys.stderr)
207|                return True
208|            except:
209|                pass
210|        print("Failed to start server.", file=sys.stderr)
211|        return False
212|    except Exception as e:
213|        print(f"Failed to start server: {e}", file=sys.stderr)
214|        return False
215|
216|
217|async def interactive_mode():
218|    """REPL mode for interactive use."""
219|    print("Browseye Interactive Mode")
220|    print("Type 'help' for commands, 'quit' to exit.")
221|    print()
222|
223|    if not ensure_server():
224|        print("Cannot connect to server. Is it running?", file=sys.stderr)
225|        return
226|
227|    history = []
228|
229|    while True:
230|        try:
231|            cmd_line = input("ffc> ").strip()
232|        except (EOFError, KeyboardInterrupt):
233|            print()
234|            break
235|
236|        if not cmd_line:
237|            continue
238|
239|        if cmd_line == 'quit' or cmd_line == 'exit':
240|            break
241|
242|        if cmd_line == 'help':
243|            print("Commands:")
244|            print("  <command> [params_json]    Execute a command")
245|            print("  status                     Check connection status")
246|            print("  history                    Show command history")
247|            print("  clear                      Clear screen")
248|            print("  help                       This help")
249|            print("  quit / exit                Exit")
250|            print()
251|            print("Available commands (send to extension):")
252|            print("  tab_list, tab_get, tab_create, tab_close, tab_activate")
253|            print("  navigate, page_eval, page_get_html, page_get_text")
254|            print("  page_screenshot, page_click, page_fill")
255|            print("  cookies_get, cookies_set, cookies_remove")
256|            print("  network_start, network_stop, network_get")
257|            print("  downloads_download, history_search")
258|            print("  window_list, window_create, page_get_forms, page_get_links")
259|            print("  storage_get_local, storage_get_page")
260|            print("  bookmarks_list, sessions_list, browser_info")
261|            print("  clipboard_read, clipboard_write, notify")
262|            print("  tab_execute_script, tab_insert_css")
263|            print("  ping, get_info")
264|            continue
265|
266|        if cmd_line == 'status':
267|            status = await check_status()
268|            if 'error' in status:
269|                print(f"Server: Error ({status['error']})")
270|            else:
271|                print(f"Server: Running")
272|                print(f"Agent connected: {status.get('agent_connected', False)}")
273|                print(f"Pending commands: {status.get('pending_commands', 0)}")
274|            continue
275|
276|        if cmd_line == 'history':
277|            for i, h in enumerate(history[-20:], 1):
278|                print(f"  {i:3d}.  {h}")
279|            continue
280|
281|        if cmd_line == 'clear':
282|            subprocess.run(['clear'] if os.name == 'posix' else ['cls'])
283|            continue
284|
285|        # Parse command and optional params
286|        parts = cmd_line.split(maxsplit=1)
287|        command = parts[0]
288|        params = {}
289|        if len(parts) > 1:
290|            try:
291|                params = json.loads(parts[1])
292|            except json.JSONDecodeError:
293|                print(f"Invalid JSON params: {parts[1]}")
294|                continue
295|
296|        history.append(cmd_line)
297|        result = await send_command(command, params)
298|        print()
299|        if result.get('success'):
300|            pretty_print(result.get('data'), False)
301|        else:
302|            print(f"Error: {result.get('error', 'unknown')}")
303|        print()
304|
305|
306|def main():
307|    parser = argparse.ArgumentParser(
308|        description='Browseye — control Firefox from the command line',
309|        formatter_class=argparse.RawDescriptionHelpFormatter,
310|        epilog="""
311|Examples:
312|  %(prog)s tab_list
313|  %(prog)s navigate '{"url": "https://example.com"}'
314|  %(prog)s page_eval '{"code": "document.title"}'
315|  %(prog)s page_screenshot
316|  %(prog)s cookies_get
317|  %(prog)s --json tab_get '{"tabId": 3}'
318|        """
319|    )
320|    parser.add_argument('command', nargs='?', help='Command to execute')
321|    parser.add_argument('params', nargs='?', default='{}', help='JSON parameters')
322|    parser.add_argument('--json', '-j', action='store_true', help='Output raw JSON')
323|    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive REPL mode')
324|    parser.add_argument('--status', '-s', action='store_true', help='Check server status')
325|    parser.add_argument('--timeout', '-t', type=int, default=30, help='Command timeout in seconds')
326|    parser.add_argument('--no-autostart', action='store_true', help="Don't auto-start the server")
327|
328|    args = parser.parse_args()
329|
330|    if args.status:
331|        status = asyncio.run(check_status())
332|        if 'error' in status:
333|            print(f"Server: OFFLINE ({status['error']})")
334|        else:
335|            print(f"Server: ONLINE")
336|            print(f"Agent connected: {status.get('agent_connected', False)}")
337|            print(f"Pending commands: {status.get('pending_commands', 0)}")
338|        return
339|
340|    if args.interactive:
341|        asyncio.run(interactive_mode())
342|        return
343|
344|    if not args.command:
345|        if args.params != '{}':
346|            print("Error: params provided without command", file=sys.stderr)
347|            sys.exit(1)
348|        parser.print_help()
349|        sys.exit(1)
350|
351|    if not args.no_autostart:
352|        ensure_server()
353|
354|    # Parse params
355|    params = {}
356|    if args.params and args.params != '{}':
357|        try:
358|            params = json.loads(args.params)
359|        except json.JSONDecodeError:
360|            print(f"Error: invalid JSON params: {args.params}", file=sys.stderr)
361|            sys.exit(1)
362|
363|    # Execute
364|    result = asyncio.run(send_command(args.command, params, timeout=args.timeout))
365|
366|    if args.json:
367|        print(json.dumps(result, indent=2, default=str))
368|    else:
369|        if result.get('success'):
370|            pretty_print(result.get('data'), False)
371|        else:
372|            print(f"Error: {result.get('error', 'unknown')}", file=sys.stderr)
373|            sys.exit(1)
374|
375|
376|if __name__ == '__main__':
377|    main()
378|
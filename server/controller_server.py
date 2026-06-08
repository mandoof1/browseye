1|#!/usr/bin/env python3
2|"""
3|Browseye — WebSocket control server
4|
5|Listens on ws://127.0.0.1:8765.
6|The Firefox extension connects as the "agent".
7|CLI tools connect as "clients" to send commands and receive responses.
8|
9|Usage:
10|    ./controller_server.py              # Run server (foreground)
11|    ./controller_server.py --daemon     # Run server (background, log to file)
12|"""
13|
14|import asyncio
15|import json
16|import logging
17|import os
18|import signal
19|import sys
20|import time
21|import uuid
22|from pathlib import Path
23|
24|logging.basicConfig(
25|    level=logging.INFO,
26|    format='[%(asctime)s] %(levelname)s %(message)s',
27|    datefmt='%H:%M:%S'
28|)
29|log = logging.getLogger('ffc-server')
30|
31|try:
32|    import websockets
33|    from websockets.exceptions import ConnectionClosed
34|    # websockets >= 13.0 uses top-level serve; websockets < 13 uses websockets.server
35|    try:
36|        from websockets.asyncio.server import serve
37|    except ImportError:
38|        from websockets.server import serve
39|except ImportError:
40|    log.error("Missing 'websockets' package. Install with: pip install websockets")
41|    sys.exit(1)
42|
43|HOST = '127.0.0.1'
44|PORT = 8765
45|
46|# ---------------------------------------------------------------------------
47|# State
48|# ---------------------------------------------------------------------------
49|
50|class AgentState:
51|    """Tracks the connected extension agent and pending commands."""
52|    def __init__(self):
53|        self.agent = None          # WebSocket for the Firefox extension
54|        self.agent_connected = asyncio.Event()
55|        self.pending = {}          # cmd_id -> (response_future, cmd_name)
56|
57|    def set_agent(self, ws):
58|        self.agent = ws
59|        self.agent_connected.set()
60|        log.info("Agent connected")
61|
62|    def clear_agent(self):
63|        self.agent = None
64|        self.agent_connected.clear()
65|        # Fail all pending commands
66|        for cid, (fut, name) in self.pending.items():
67|            if not fut.done():
68|                fut.set_exception(ConnectionError(f"Agent disconnected before completing: {name}"))
69|        self.pending.clear()
70|        log.warning("Agent disconnected")
71|
72|    async def send_command(self, command: str, params: dict = None, timeout: float = 30.0) -> dict:
73|        """Send a command to the agent and wait for response."""
74|        try:
75|            await asyncio.wait_for(self.agent_connected.wait(), timeout=10.0)
76|        except asyncio.TimeoutError:
77|            raise ConnectionError("No agent (Firefox extension) connected. Start server first, then load the extension in Firefox.")
78|        if not self.agent:
79|            raise ConnectionError("No agent connected")
80|
81|        cmd_id = str(uuid.uuid4())
82|        msg = json.dumps({
83|            'id': cmd_id,
84|            'command': command,
85|            'params': params or {}
86|        })
87|
88|        loop = asyncio.get_event_loop()
89|        future = loop.create_future()
90|        self.pending[cmd_id] = (future, command)
91|
92|        try:
93|            await self.agent.send(msg)
94|            # Wait with timeout
95|            result = await asyncio.wait_for(future, timeout=timeout)
96|            return result
97|        except asyncio.TimeoutError:
98|            self.pending.pop(cmd_id, None)
99|            raise TimeoutError(f"Command '{command}' timed out after {timeout}s")
100|        finally:
101|            self.pending.pop(cmd_id, None)
102|
103|    def deliver_response(self, cmd_id: str, data: dict):
104|        """Route a response from the agent to the waiting client."""
105|        if cmd_id in self.pending:
106|            future, name = self.pending[cmd_id]
107|            if not future.done():
108|                future.set_result(data)
109|
110|
111|state = AgentState()
112|
113|# ---------------------------------------------------------------------------
114|# WebSocket handlers
115|# ---------------------------------------------------------------------------
116|
117|async def handle_agent(websocket):
118|    """Handler for the Firefox extension agent connection."""
119|    log.info("New agent connection attempt")
120|
121|    # If we already have an agent, replace it
122|    if state.agent:
123|        old = state.agent
124|        state.clear_agent()
125|        try:
126|            await old.close(1012, "Replaced by new agent")
127|        except Exception:
128|            pass
129|
130|    state.set_agent(websocket)
131|
132|    try:
133|        async for raw in websocket:
134|            try:
135|                data = json.loads(raw)
136|            except json.JSONDecodeError:
137|                log.warning(f"Invalid JSON from agent: {raw[:200]}")
138|                continue
139|
140|            msg_type = data.get('type')
141|
142|            if msg_type == 'agent_hello':
143|                log.info(f"Agent hello: {data.get('agent')} v{data.get('version')}")
144|
145|            elif msg_type == 'response':
146|                cmd_id = data.get('id')
147|                if cmd_id:
148|                    state.deliver_response(cmd_id, data)
149|                else:
150|                    log.warning(f"Response without id: {data}")
151|
152|            elif msg_type == 'status_update':
153|                log.info(f"Agent status: {data.get('status')}")
154|
155|            else:
156|                log.debug(f"Unhandled agent message: {msg_type}")
157|    except ConnectionClosed:
158|        pass
159|    finally:
160|        state.clear_agent()
161|
162|
163|async def handle_client(websocket):
164|    """Handler for CLI/client connections."""
165|    log.info("Client connected")
166|    try:
167|        async for raw in websocket:
168|            try:
169|                data = json.loads(raw)
170|            except json.JSONDecodeError:
171|                await websocket.send(json.dumps({
172|                    'type': 'error',
173|                    'error': 'Invalid JSON'
174|                }))
175|                continue
176|
177|            msg_type = data.get('type')
178|
179|            if msg_type == 'command':
180|                cmd = data.get('command')
181|                cmd_id = data.get('id', str(uuid.uuid4()))
182|                params = data.get('params', {})
183|                timeout = data.get('timeout', 30.0)
184|
185|                # Server-side handled commands (no agent needed)
186|                if cmd == 'ping' and not state.agent:
187|                    await websocket.send(json.dumps({
188|                        'type': 'response',
189|                        'id': cmd_id,
190|                        'command': cmd,
191|                        'success': True,
192|                        'data': {'pong': True, 'ts': int(time.time() * 1000), 'agent_connected': False}
193|                    }))
194|                    continue
195|
196|                log.info(f"Command: {cmd} (id={cmd_id[:8]}... timeout={timeout}s)")
197|
198|                try:
199|                    result = await state.send_command(cmd, params, timeout=timeout)
200|                    await websocket.send(json.dumps({
201|                        'type': 'response',
202|                        'id': cmd_id,
203|                        'command': cmd,
204|                        'success': result.get('success', True),
205|                        'data': result.get('data'),
206|                        'error': result.get('error')
207|                    }))
208|                except TimeoutError as e:
209|                    await websocket.send(json.dumps({
210|                        'type': 'response',
211|                        'id': cmd_id,
212|                        'command': cmd,
213|                        'success': False,
214|                        'error': str(e)
215|                    }))
216|                except ConnectionError as e:
217|                    await websocket.send(json.dumps({
218|                        'type': 'response',
219|                        'id': cmd_id,
220|                        'command': cmd,
221|                        'success': False,
222|                        'error': str(e)
223|                    }))
224|                except Exception as e:
225|                    log.exception(f"Command error: {cmd}")
226|                    await websocket.send(json.dumps({
227|                        'type': 'response',
228|                        'id': cmd_id,
229|                        'command': cmd,
230|                        'success': False,
231|                        'error': f"Server error: {str(e)}"
232|                    }))
233|
234|            elif msg_type == 'ping':
235|                await websocket.send(json.dumps({
236|                    'type': 'pong',
237|                    'id': data.get('id', ''),
238|                    'agent_connected': state.agent is not None
239|                }))
240|
241|            elif msg_type == 'status':
242|                await websocket.send(json.dumps({
243|                    'type': 'status',
244|                    'agent_connected': state.agent is not None,
245|                    'pending_commands': len(state.pending)
246|                }))
247|
248|            else:
249|                await websocket.send(json.dumps({
250|                    'type': 'error',
251|                    'error': f"Unknown message type: {msg_type}"
252|                }))
253|    except ConnectionClosed:
254|        pass
255|    finally:
256|        log.info("Client disconnected")
257|
258|
259|# ---------------------------------------------------------------------------
260|# Main
261|# ---------------------------------------------------------------------------
262|
263|async def main():
264|    # Handle SIGINT/SIGTERM gracefully
265|    stop = asyncio.Future()
266|
267|    def signal_handler():
268|        if not stop.done():
269|            stop.set_result(True)
270|
271|    loop = asyncio.get_event_loop()
272|    loop.add_signal_handler(signal.SIGINT, signal_handler)
273|    loop.add_signal_handler(signal.SIGTERM, signal_handler)
274|
275|    async with serve(handle_agent, HOST, PORT) as agent_server:
276|        async with serve(handle_client, HOST, PORT + 1) as client_server:
277|            log.info(f"Browseye Server")
278|            log.info(f"  Agent endpoint:   ws://{HOST}:{PORT}")
279|            log.info(f"  Client endpoint:  ws://{HOST}:{PORT + 1}")
280|            log.info(f"  Waiting for Firefox extension to connect...")
281|            log.info(f"  Press Ctrl+C to stop")
282|
283|            await stop
284|
285|    log.info("Server stopped")
286|
287|    # Cleanup
288|    if state.agent:
289|        try:
290|            await state.agent.close(1001, "Server shutting down")
291|        except Exception:
292|            pass
293|
294|
295|if __name__ == '__main__':
296|    if '--daemon' in sys.argv:
297|        # Fork to background
298|        pid = os.fork()
299|        if pid > 0:
300|            print(f"Server started in background (PID: {pid})")
301|            sys.exit(0)
302|
303|        # Child: detach and run
304|        os.setsid()
305|        # Redirect stdout/stderr to log file
306|        log_dir = Path.home() / '.browseye'
307|        log_dir.mkdir(parents=True, exist_ok=True)
308|        log_file = log_dir / 'server.log'
309|        f = open(log_file, 'a')
310|        sys.stdout = f
311|        sys.stderr = f
312|
313|    asyncio.run(main())
314|
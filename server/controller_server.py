#!/usr/bin/env python3
"""
Browseye — WebSocket control server

Listens on ws://127.0.0.1:8765.
The Firefox extension connects as the "agent".
CLI tools connect as "clients" to send commands and receive responses.

Usage:
    ./controller_server.py              # Run server (foreground)
    ./controller_server.py --daemon     # Run server (background, log to file)
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('ffc-server')

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    # websockets >= 13.0 uses top-level serve; websockets < 13 uses websockets.server
    try:
        from websockets.asyncio.server import serve
    except ImportError:
        from websockets.server import serve
except ImportError:
    log.error("Missing 'websockets' package. Install with: pip install websockets")
    sys.exit(1)

HOST = '127.0.0.1'
PORT = 8765

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState:
    """Tracks the connected extension agent and pending commands."""
    def __init__(self):
        self.agent = None          # WebSocket for the Firefox extension
        self.agent_connected = asyncio.Event()
        self.pending = {}          # cmd_id -> (response_future, cmd_name)

    def set_agent(self, ws):
        self.agent = ws
        self.agent_connected.set()
        log.info("Agent connected")

    def clear_agent(self):
        self.agent = None
        self.agent_connected.clear()
        # Fail all pending commands
        for cid, (fut, name) in self.pending.items():
            if not fut.done():
                fut.set_exception(ConnectionError(f"Agent disconnected before completing: {name}"))
        self.pending.clear()
        log.warning("Agent disconnected")

    async def send_command(self, command: str, params: dict = None, timeout: float = 30.0) -> dict:
        """Send a command to the agent and wait for response."""
        try:
            await asyncio.wait_for(self.agent_connected.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError("No agent (Firefox extension) connected. Start server first, then load the extension in Firefox.")
        if not self.agent:
            raise ConnectionError("No agent connected")

        cmd_id = str(uuid.uuid4())
        msg = json.dumps({
            'id': cmd_id,
            'command': command,
            'params': params or {}
        })

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending[cmd_id] = (future, command)

        try:
            await self.agent.send(msg)
            # Wait with timeout
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.pending.pop(cmd_id, None)
            raise TimeoutError(f"Command '{command}' timed out after {timeout}s")
        finally:
            self.pending.pop(cmd_id, None)

    def deliver_response(self, cmd_id: str, data: dict):
        """Route a response from the agent to the waiting client."""
        if cmd_id in self.pending:
            future, name = self.pending[cmd_id]
            if not future.done():
                future.set_result(data)


state = AgentState()

# ---------------------------------------------------------------------------
# WebSocket handlers
# ---------------------------------------------------------------------------

async def handle_agent(websocket):
    """Handler for the Firefox extension agent connection."""
    log.info("New agent connection attempt")

    # If we already have an agent, replace it
    if state.agent:
        old = state.agent
        state.clear_agent()
        try:
            await old.close(1012, "Replaced by new agent")
        except Exception:
            pass

    state.set_agent(websocket)

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON from agent: {raw[:200]}")
                continue

            msg_type = data.get('type')

            if msg_type == 'agent_hello':
                log.info(f"Agent hello: {data.get('agent')} v{data.get('version')}")

            elif msg_type == 'response':
                cmd_id = data.get('id')
                if cmd_id:
                    state.deliver_response(cmd_id, data)
                else:
                    log.warning(f"Response without id: {data}")

            elif msg_type == 'status_update':
                log.info(f"Agent status: {data.get('status')}")

            else:
                log.debug(f"Unhandled agent message: {msg_type}")
    except ConnectionClosed:
        pass
    finally:
        state.clear_agent()


async def handle_client(websocket):
    """Handler for CLI/client connections."""
    log.info("Client connected")
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'error': 'Invalid JSON'
                }))
                continue

            msg_type = data.get('type')

            if msg_type == 'command':
                cmd = data.get('command')
                cmd_id = data.get('id', str(uuid.uuid4()))
                params = data.get('params', {})
                timeout = data.get('timeout', 30.0)

                # Server-side handled commands (no agent needed)
                if cmd == 'ping' and not state.agent:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'id': cmd_id,
                        'command': cmd,
                        'success': True,
                        'data': {'pong': True, 'ts': int(time.time() * 1000), 'agent_connected': False}
                    }))
                    continue

                log.info(f"Command: {cmd} (id={cmd_id[:8]}... timeout={timeout}s)")

                try:
                    result = await state.send_command(cmd, params, timeout=timeout)
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'id': cmd_id,
                        'command': cmd,
                        'success': result.get('success', True),
                        'data': result.get('data'),
                        'error': result.get('error')
                    }))
                except TimeoutError as e:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'id': cmd_id,
                        'command': cmd,
                        'success': False,
                        'error': str(e)
                    }))
                except ConnectionError as e:
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'id': cmd_id,
                        'command': cmd,
                        'success': False,
                        'error': str(e)
                    }))
                except Exception as e:
                    log.exception(f"Command error: {cmd}")
                    await websocket.send(json.dumps({
                        'type': 'response',
                        'id': cmd_id,
                        'command': cmd,
                        'success': False,
                        'error': f"Server error: {str(e)}"
                    }))

            elif msg_type == 'ping':
                await websocket.send(json.dumps({
                    'type': 'pong',
                    'id': data.get('id', ''),
                    'agent_connected': state.agent is not None
                }))

            elif msg_type == 'status':
                await websocket.send(json.dumps({
                    'type': 'status',
                    'agent_connected': state.agent is not None,
                    'pending_commands': len(state.pending)
                }))

            else:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'error': f"Unknown message type: {msg_type}"
                }))
    except ConnectionClosed:
        pass
    finally:
        log.info("Client disconnected")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    # Handle SIGINT/SIGTERM gracefully
    stop = asyncio.Future()

    def signal_handler():
        if not stop.done():
            stop.set_result(True)

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    async with serve(handle_agent, HOST, PORT) as agent_server:
        async with serve(handle_client, HOST, PORT + 1) as client_server:
            log.info(f"Browseye Server")
            log.info(f"  Agent endpoint:   ws://{HOST}:{PORT}")
            log.info(f"  Client endpoint:  ws://{HOST}:{PORT + 1}")
            log.info(f"  Waiting for Firefox extension to connect...")
            log.info(f"  Press Ctrl+C to stop")

            await stop

    log.info("Server stopped")

    # Cleanup
    if state.agent:
        try:
            await state.agent.close(1001, "Server shutting down")
        except Exception:
            pass


if __name__ == '__main__':
    if '--daemon' in sys.argv:
        # Fork to background
        pid = os.fork()
        if pid > 0:
            print(f"Server started in background (PID: {pid})")
            sys.exit(0)

        # Child: detach and run
        os.setsid()
        # Redirect stdout/stderr to log file
        log_dir = Path.home() / '.browseye'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'server.log'
        f = open(log_file, 'a')
        sys.stdout = f
        sys.stderr = f

    asyncio.run(main())

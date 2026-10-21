"""Small device MCP transport; payloads and credentials are never logged."""
from __future__ import annotations
import asyncio


class DeviceLink:
    def __init__(self, send, on_ready=None, timeout=8):
        self.send = send
        self.on_ready = on_ready
        self.timeout = timeout
        self.tools = {}
        self.ready = asyncio.Event()
        self.pending = {}
        self.next_id = 1000
        self.bootstrap = None
        self.failed = False
        self.closed = False

    def start(self):
        self.bootstrap = asyncio.create_task(self._bootstrap())

    async def _bootstrap(self):
        try:
            await self._request('initialize', {
                'protocolVersion': '2024-11-05', 'capabilities': {},
                'clientInfo': {'name': 'XiaoZhiLocalHardware', 'version': '1.0'}})
            cursor = ''
            for _ in range(20):
                result = await self._request('tools/list', {'withUserTools': True, 'cursor': cursor})
                if not isinstance(result, dict) or not isinstance(result.get('tools'), list):
                    raise ValueError('Invalid device tool list')
                for tool in result['tools']:
                    if isinstance(tool, dict) and isinstance(tool.get('name'), str):
                        self.tools[tool['name']] = tool
                next_cursor = result.get('nextCursor')
                if not next_cursor:
                    break
                if not isinstance(next_cursor, str) or next_cursor == cursor:
                    raise ValueError('Invalid pagination cursor')
                cursor = next_cursor
            else:
                raise ValueError('Too many device tool pages')
            self.ready.set()
            if self.on_ready:
                self.on_ready(self)
        except Exception:
            self.failed = True

    async def wait_ready(self):
        await asyncio.wait_for(self.ready.wait(), self.timeout)

    async def _request(self, method, params):
        if self.closed:
            raise RuntimeError('Device link closed')
        request_id = self.next_id
        self.next_id += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self.pending.pop(request_id, None)
            if not future.done():
                future.cancel()

    def receive(self, payload):
        if not isinstance(payload, dict):
            return
        request_id = payload.get('id')
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            return
        future = self.pending.get(request_id)
        if not future or future.done():
            return
        if 'error' in payload:
            future.set_exception(RuntimeError('Device rejected RPC'))
        elif 'result' in payload:
            future.set_result(payload['result'])

    async def call_tool(self, name, arguments):
        await self.wait_ready()
        if name not in self.tools:
            raise LookupError('Device tool is unavailable')
        schema = self.tools[name].get('inputSchema') or {}
        properties = schema.get('properties', {})
        if any(key not in properties for key in arguments):
            raise ValueError('Unknown device argument')
        if any(key not in arguments for key in schema.get('required', [])):
            raise ValueError('Missing device argument')
        for key, value in arguments.items():
            spec = properties[key]
            expected = spec.get('type')
            if expected == 'integer' and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError('Invalid integer argument')
            if expected == 'string' and not isinstance(value, str):
                raise ValueError('Invalid string argument')
            if isinstance(value, (int, float)):
                if value < spec.get('minimum', float('-inf')) or value > spec.get('maximum', float('inf')):
                    raise ValueError('Argument out of range')
            if 'enum' in spec and value not in spec['enum']:
                raise ValueError('Argument not in enum')
        raw = await self._request('tools/call', {'name': name, 'arguments': arguments})
        if not isinstance(raw, dict) or raw.get('isError'):
            raise RuntimeError('Device did not confirm tool execution')
        content = raw.get('content', [])
        if not content or not isinstance(content[0], dict) or 'text' not in content[0]:
            raise ValueError('Device reply is missing text')
        return content[0]['text']

    async def close(self):
        self.closed = True
        if self.bootstrap and not self.bootstrap.done():
            self.bootstrap.cancel()
            await asyncio.gather(self.bootstrap, return_exceptions=True)
        for future in list(self.pending.values()):
            if not future.done():
                future.cancel()
        self.pending.clear()

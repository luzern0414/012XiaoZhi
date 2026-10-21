"""Project-owned text stream extension to the XiaoZhi protocol."""
from __future__ import annotations
import time


def retry_before_output(factory, active, pause=None):
    """One bounded retry for transient failures before the first output chunk."""
    pause = pause or (lambda: time.sleep(1))
    for attempt in range(2):
        if not active():
            return
        emitted = False
        source = None
        try:
            source = factory()
            for chunk in source:
                if not active():
                    return
                emitted = True
                yield chunk
            return
        except Exception as error:
            status = getattr(error, 'status_code', None)
            transient = status in (408, 429, 500, 502, 503, 504) or any(
                word in str(error).lower() for word in ('overloaded', 'temporarily unavailable', 'timed out'))
            if attempt or emitted or not transient:
                raise
        finally:
            close = getattr(source, 'close', None)
            if close:
                close()
        pause()


class TurnExecutor:
    """Bind chat work to the generation at submission, including queued work."""
    def __init__(self, executor, owner):
        self.executor, self.owner = executor, owner

    def __getattr__(self, name):
        return getattr(self.executor, name)

    def submit(self, function, *args, **kwargs):
        owner = self.owner
        if getattr(function, '__self__', None) is not owner or getattr(function, '__name__', '') != 'chat':
            return self.executor.submit(function, *args, **kwargs)
        turn = getattr(owner, 'control_turn', None)
        accepted = turn.get() if turn is not None else None
        generation = getattr(owner.control_worker, 'generation',
            owner.control_generation if accepted is None else accepted)
        def run():
            if not owner.control_gate.enabled or generation != owner.control_generation:
                return None
            previous = getattr(owner.control_worker, 'generation', None)
            owner.control_worker.generation = generation
            try:
                return function(*args, **kwargs)
            finally:
                if previous is None:
                    del owner.control_worker.generation
                else:
                    owner.control_worker.generation = previous
        return self.executor.submit(run)


def guarded_source(factory, active):
    if not active():
        return
    source = factory()
    try:
        while active():
            try:
                chunk = next(source)
            except StopIteration:
                return
            if not active():
                return
            yield chunk
    finally:
        close = getattr(source, 'close', None)
        if close:
            close()


class StreamRelay:
    def __init__(self, emit, active, request_id):
        self.emit, self.active, self.request_id = emit, active, request_id

    def event(self, state, **fields):
        if self.active():
            self.emit(dict(type='text_stream', state=state,
                           request_id=self.request_id, **fields))

    def forward(self, source):
        self.event('start')
        try:
            for chunk in source:
                if not self.active():
                    break
                if chunk:
                    self.event('delta', text=chunk)
                yield chunk
            self.event('end')
        except Exception:
            self.event('error', text='回答生成失败，请重试。')
            raise
        finally:
            close = getattr(source, 'close', None)
            if close:
                close()


def install(server_module, runtime):
    """Wrap each connection's provider; never modify the shared provider."""
    import asyncio
    import json
    import time
    import uuid
    from pathlib import Path

    base = server_module.ConnectionHandler
    devices = {}
    hardware_mac = '90:e5:b1:d6:40:5c'

    def persist():
        target = Path(runtime) / 'devices.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'updated_at': time.time(),
                                         'devices': list(devices.values())}), encoding='utf-8')
        temporary.replace(target)

    class Provider:
        def __init__(self, provider, conn):
            self.provider, self.conn = provider, conn

        def __getattr__(self, name):
            return getattr(self.provider, name)

        def response_with_functions(self, *args, **kwargs):
            conn = self.conn
            gate = getattr(conn, 'control_gate', None)
            worker = getattr(conn, 'control_worker', None)
            generation = getattr(worker, 'generation', getattr(conn, 'control_generation', None))
            return guarded_source(lambda: self.provider.response_with_functions(*args, **kwargs),
                lambda: gate is None or (gate.enabled and generation == conn.control_generation))

        def response(self, *args, **kwargs):
            conn = self.conn
            gate = getattr(conn, 'control_gate', None)
            worker = getattr(conn, 'control_worker', None)
            generation = getattr(worker, 'generation', getattr(conn, 'control_generation', None))
            permitted = lambda: (not conn.client_abort and not conn.stop_event.is_set() and
                (gate is None or (gate.enabled and generation == conn.control_generation)))
            source = guarded_source(lambda: retry_before_output(
                lambda: self.provider.response(*args, **kwargs), permitted), permitted)
            if not (conn.features or {}).get('text_stream'):
                return source
            turn = conn.sentence_id
            active = lambda: not conn.client_abort and conn.sentence_id == turn and not conn.stop_event.is_set()
            def emit(event):
                async def send():
                    if active():
                        await conn.websocket.send(json.dumps(event, ensure_ascii=False))
                future = asyncio.run_coroutine_threadsafe(send(), conn.loop)
                try:
                    future.result(timeout=5)
                except Exception:
                    future.cancel()
                    raise
            return StreamRelay(emit, active, turn or uuid.uuid4().hex).forward(source)

    class StreamingConnection(base):
        @property
        def llm(self):
            return self._stream_llm

        @llm.setter
        def llm(self, value):
            self._stream_llm = Provider(value, self) if value is not None else None

        async def handle_connection(self, ws):
            device_id = ws.request.headers.get('device-id', '').lower()
            known = device_id == hardware_mac
            if known:
                devices[self.session_id] = dict(device_id=device_id,
                    connected_at=time.time(), ip=ws.remote_address[0], connected=True)
                persist()
            try:
                return await super().handle_connection(ws)
            finally:
                if known:
                    devices.pop(self.session_id, None)
                    persist()

    persist()
    server_module.ConnectionHandler = StreamingConnection

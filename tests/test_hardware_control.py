import asyncio
import sys
from types import ModuleType, SimpleNamespace
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
import threading

from src.device_control import AssistantGate, Outcome
from src.hardware_control import install
from src.streaming import TurnExecutor


def test_accepted_chat_keeps_intent_generation_during_stt_send(monkeypatch, tmp_path):
    async def run():
        conn = adapter(monkeypatch, tmp_path)
        conn.control_gate = AssistantGate()
        conn.control_gate.route(SimpleNamespace(kind='assistant_on'))
        conn.control_generation = 0
        conn.control_lock = asyncio.Lock()
        conn.control_job = None
        conn.control_device = None
        conn.control_worker = threading.local()
        conn.control_turn = ContextVar('accepted_turn', default=None)
        conn._persist_control = lambda: None
        async def quiet(*args):
            pass
        conn._stop_output = quiet
        conn._control_feedback = quiet
        calls = []
        # A bound method is how upstream submits chat to the connection executor.
        def chat(self, text):
            calls.append(text)
        conn.__class__.chat = chat
        entered, release = asyncio.Event(), asyncio.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            conn.executor = TurnExecutor(executor, conn)
            async def upstream_chat_path():
                assert not await conn._control_intent('一加一等于几')
                assert conn.control_turn.get() == conn.control_generation
                entered.set()
                await release.wait()  # startToChat's send_stt_message await
                await asyncio.wrap_future(conn.executor.submit(conn.chat, 'old question'))
            old = asyncio.create_task(upstream_chat_path())
            await entered.wait()
            await conn._control_intent('关闭语音助手')
            await conn._control_intent('打开语音助手')
            release.set()
            await old
        assert calls == []
        assert conn.control_gate.enabled
    asyncio.run(run())


def adapter(monkeypatch, tmp_path):
    audio = ModuleType('core.handle.receiveAudioHandle')
    async def previous(conn, text):
        return False
    audio.handle_user_intent = previous
    core = ModuleType('core')
    handle = ModuleType('core.handle')
    handle.receiveAudioHandle = audio
    abort = ModuleType('core.handle.abortHandle')
    abort.handleAbortMessage = previous
    intent = ModuleType('core.handle.intentHandler')
    intent.speak_txt = lambda *args: None
    send = ModuleType('core.handle.sendAudioHandle')
    send.send_tts_message = previous
    for name, value in {'core': core, 'core.handle': handle,
        'core.handle.receiveAudioHandle': audio, 'core.handle.abortHandle': abort,
        'core.handle.intentHandler': intent, 'core.handle.sendAudioHandle': send}.items():
        monkeypatch.setitem(sys.modules, name, value)
    server = SimpleNamespace(ConnectionHandler=type('Base', (), {}))
    install(server, tmp_path)
    return server.ConnectionHandler()


def test_control_feedback_starts_speaking_and_displays_text_before_audio(monkeypatch, tmp_path):
    async def run():
        conn = adapter(monkeypatch, tmp_path)
        conn.control_gate = AssistantGate()
        conn.control_gate.enabled = True
        conn.tts = object()
        events = []
        async def tts(conn, state, text=None):
            events.append((state, text))
        module = sys.modules['core.handle.sendAudioHandle']
        module.send_tts_message = tts
        sys.modules['core.handle.intentHandler'].speak_txt = lambda conn, text: events.append(('audio', text))
        # Reinstall to bind the patched protocol functions.
        server = SimpleNamespace(ConnectionHandler=type('Base', (), {}))
        install(server, tmp_path)
        conn.__class__ = server.ConnectionHandler
        await conn._control_feedback(Outcome('当前音量是 70%。'))
        assert events == [('start', None), ('sentence_start', '当前音量是 70%。'),
                          ('audio', '当前音量是 70%。')]
    asyncio.run(run())


def test_text_only_feedback_does_not_switch_hardware_to_speaking(monkeypatch, tmp_path):
    async def run():
        conn = adapter(monkeypatch, tmp_path)
        conn.control_gate = AssistantGate()
        events = []
        async def tts(conn, state, text=None):
            events.append((state, text))
        sys.modules['core.handle.sendAudioHandle'].send_tts_message = tts
        server = SimpleNamespace(ConnectionHandler=type('Base', (), {}))
        install(server, tmp_path)
        conn.__class__ = server.ConnectionHandler
        await conn._control_feedback(Outcome('语音助手已关闭', speech=False))
        assert events == [('sentence_start', '语音助手已关闭')]
    asyncio.run(run())


def test_disabled_or_superseded_control_cannot_execute(monkeypatch, tmp_path):
    async def run():
        conn = adapter(monkeypatch, tmp_path)
        conn.control_gate = AssistantGate()
        conn.control_generation = 2
        calls = []
        async def wait():
            pass
        async def execute(command):
            calls.append(command)
        conn.control_link = SimpleNamespace(wait_ready=wait)
        conn.control_device = SimpleNamespace(execute=execute)
        await conn._run_control(SimpleNamespace(kind='volume_set'), 2)
        conn.control_gate.enabled = True
        await conn._run_control(SimpleNamespace(kind='volume_set'), 1)
        assert calls == []
    asyncio.run(run())


def test_close_cancels_command_waiting_for_device_without_late_execution(monkeypatch, tmp_path):
    async def run():
        conn = adapter(monkeypatch, tmp_path)
        conn.control_gate = AssistantGate()
        conn.control_gate.route(SimpleNamespace(kind='assistant_on'))
        conn.control_generation = 0
        conn.control_lock = asyncio.Lock()
        conn.control_job = None
        ready = asyncio.Event()
        calls = []
        async def execute(command):
            calls.append(command)
        conn.control_link = SimpleNamespace(wait_ready=ready.wait)
        conn.control_device = SimpleNamespace(execute=execute, pending_reboot=None)
        async def stop():
            await asyncio.sleep(.01)
        async def feedback(result):
            pass
        conn._stop_output = stop
        conn._control_feedback = feedback
        conn._persist_control = lambda: None
        old = asyncio.create_task(conn._control_intent('音量调到五十'))
        await asyncio.sleep(.001)
        close = asyncio.create_task(conn._control_intent('关闭语音助手'))
        await asyncio.gather(old, close)
        ready.set()
        await asyncio.sleep(.01)
        assert not conn.control_gate.enabled
        assert calls == []
    asyncio.run(run())

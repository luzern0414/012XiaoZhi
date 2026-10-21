"""Hardware-first voice control adapter, without modifying upstream files."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import time
import threading
import uuid
from contextvars import ContextVar

from src.device_control import AssistantGate, DeviceController, Outcome, parse_command
from src.device_link import DeviceLink
from src.streaming import TurnExecutor
from src.hardware_display import DisplaySocket


def install(server_module, runtime):
    from core.handle import receiveAudioHandle as audio
    from core.handle.abortHandle import handleAbortMessage
    from core.handle.intentHandler import speak_txt
    from core.handle.sendAudioHandle import send_tts_message

    runtime = Path(runtime)
    base = server_module.ConnectionHandler
    previous_intent = audio.handle_user_intent

    class HardwareConnection(base):
        async def handle_connection(self, ws):
            self.control_gate = AssistantGate()
            self.control_job = None
            self.control_generation = 0
            self.control_lock = asyncio.Lock()
            self.control_worker = threading.local()
            self.control_turn = ContextVar('chat_generation', default=None)
            self.executor = TurnExecutor(self.executor, self)
            self.control_link = None
            self.control_probe = None
            self.control_device = None
            self.control_hello = False
            self.control_connected = True
            self.control_hardware = (ws.request.headers.get('device-id', '').lower() == '90:e5:b1:d6:40:5c'
                                     and ws.remote_address[0] == '192.168.16.22')
            # Scoped protocol acceptance simulator; cannot address the physical connection.
            self.control_test = (ws.remote_address[0] in ('127.0.0.1', '::1') and
                ws.request.headers.get('client-id') == 'hardware-acceptance')
            self.config.update(enable_greeting=False, enable_wakeup_words_response_cache=False,
                               enable_stop_tts_notify=False, end_prompt={'enable': False})
            self.config['cmd_exit'] = []
            timer = asyncio.create_task(self._control_timer())
            display_socket = DisplaySocket(ws, self) if self.control_hardware or self.control_test else None
            try:
                return await super().handle_connection(display_socket or ws)
            finally:
                self.control_connected = False
                self.control_gate.enabled = False
                await self._cancel_control()
                timer.cancel()
                await asyncio.gather(timer, return_exceptions=True)
                if display_socket:
                    await display_socket.finish()
                if self.control_link:
                    await self.control_link.close()
                if self.control_probe:
                    self.control_probe.cancel()
                    await asyncio.gather(self.control_probe, return_exceptions=True)
                self._persist_control()

        def _persist_control(self):
            if self.control_hardware:
                target = runtime / 'hardware-control.json'
                state = dict(at=time.time(), connected=self.control_connected,
                    enabled=self.control_gate.enabled, idle_seconds=self.control_gate.idle_seconds,
                    mcp_ready=bool(self.control_link and self.control_link.ready.is_set()))
                temporary = target.with_suffix('.tmp')
                temporary.write_text(json.dumps(state), encoding='utf-8')
                temporary.replace(target)

        def _capabilities(self, link):
            if self.control_hardware:
                (runtime/'hardware-capabilities.json').write_text(json.dumps(dict(
                    at=time.time(), tools=[dict(name=t['name'], inputSchema=t.get('inputSchema', {}))
                    for t in link.tools.values()]), ensure_ascii=False, indent=2), encoding='utf-8')
            self._persist_control()
            if self.control_hardware:
                self.control_probe = asyncio.create_task(self._probe_status())

        async def _probe_status(self):
            """Read-only diagnostics. Never activate, speak or retain raw device payloads."""
            try:
                raw = await self.control_link.call_tool('self.get_device_status', {})
                status = json.loads(raw)
                summary = dict(at=time.time(), source='physical_device_mcp', ip='192.168.16.22')
                for section, fields in {
                    'audio_speaker': ('volume',), 'screen': ('brightness', 'theme'),
                    'battery': ('level', 'charging'), 'network': ('type', 'signal', 'rssi')}.items():
                    value = status.get(section, {})
                    if isinstance(value, dict):
                        summary[section] = {key: value[key] for key in fields
                            if isinstance(value.get(key), (str, int, float, bool))}
                (runtime/'hardware-status.json').write_text(json.dumps(summary), encoding='utf-8')
            except Exception:
                pass
            # One-shot local diagnostic, only when explicitly requested on disk.
            marker = runtime/'hardware-screen-request'
            if marker.exists() and 'self.screen.snapshot' in self.control_link.tools:
                marker.unlink(missing_ok=True)
                try:
                    await self.control_link.call_tool('self.screen.snapshot', {
                        'url': 'http://192.168.16.73:8003/hardware/screen-capture', 'quality': 85})
                except Exception:
                    (runtime/'hardware-screen-failed').write_text('snapshot unavailable', encoding='utf-8')

        async def _capture_answer_screen(self):
            marker = runtime/'hardware-screen-after-reply'
            if not self.control_hardware or not marker.exists() or not self.control_link:
                return
            if 'self.screen.snapshot' not in self.control_link.tools:
                return
            marker.unlink(missing_ok=True)
            try:
                await self.control_link.call_tool('self.screen.snapshot', {
                    'url': 'http://192.168.16.73:8003/hardware/screen-capture', 'quality': 85})
            except Exception:
                pass

        async def _route_message(self, message):
            try:
                event = json.loads(message) if isinstance(message, str) else None
            except (ValueError, TypeError):
                event = None
            if isinstance(event, dict):
                if event.get('type') == 'hello':
                    if self.control_hello:
                        return
                    self.control_hello = True
                    features = event.get('features') or {}
                    # Own the MCP lifecycle to avoid ID collisions and logging device data.
                    await asyncio.wait_for(self.bind_completed_event.wait(), 15)
                    clean = dict(event, features=dict(features, mcp=False))
                    await super()._route_message(json.dumps(clean))
                    self.features = dict(features)
                    if features.get('mcp') and (self.control_hardware or self.control_test):
                        async def send(payload):
                            await self.websocket.send(json.dumps({'type': 'mcp', 'payload': payload}))
                        self.control_link = DeviceLink(send, self._capabilities)
                        self.control_device = DeviceController(lambda: self.control_link.tools, self.control_link.call_tool)
                        self.control_link.start()
                    # One quiet screen message, never a spontaneous spoken greeting.
                    await self._control_feedback(Outcome('语音助手待机。说“打开语音助手”开始。', speech=False))
                    self._persist_control()
                    return
                if event.get('type') == 'mcp':
                    if self.control_link:
                        self.control_link.receive(event.get('payload'))
                    return
                if event.get('type') == 'listen' and event.get('state') == 'detect':
                    # Bypass wake-word cache, idle chatter and arbitrary [device_call] speech.
                    if not self.control_hello:
                        return
                    self.last_activity_time = time.time() * 1000
                    await audio.startToChat(self, event.get('text', ''))
                    return
            return await super()._route_message(message)

        async def _cancel_control(self):
            self.control_generation += 1
            if self.control_job and not self.control_job.done():
                self.control_job.cancel()
                await asyncio.gather(self.control_job, return_exceptions=True)
            self.control_job = None
            if self.control_device:
                self.control_device.pending_reboot = None

        async def _stop_output(self):
            self.sentence_id = uuid.uuid4().hex
            await handleAbortMessage(self)

        async def _control_feedback(self, result):
            self.sentence_id = uuid.uuid4().hex
            self.control_display_text = (self.sentence_id, result.text)
            if result.speech and self.control_gate.enabled and self.tts:
                self.client_abort = False
                # Control replies bypass upstream send_stt_message, which normally
                # starts speaking. Without this event firmware remains listening.
                await send_tts_message(self, 'start')
                self.client_is_speaking = True
                await send_tts_message(self, 'sentence_start', result.text)
                # speak_txt only enqueues DTOs; keep this atomic with gate transitions.
                speak_txt(self, result.text)
            else:
                # Updating text alone must not simulate speaking/listening changes.
                await send_tts_message(self, 'sentence_start', result.text)

        async def _run_control(self, command, generation):
            try:
                if generation != self.control_generation or not self.control_gate.enabled:
                    return
                if not self.control_link:
                    result = Outcome('设备未建立控制接口，请先从硬件唤醒并连接。', False)
                else:
                    await self.control_link.wait_ready()
                    if generation != self.control_generation or not self.control_gate.enabled:
                        return
                    result = await self.control_device.execute(command)
                async with self.control_lock:
                    if generation == self.control_generation and self.control_gate.enabled:
                        await self._control_feedback(result)
            except asyncio.CancelledError:
                raise
            except Exception:
                async with self.control_lock:
                    if generation == self.control_generation and self.control_gate.enabled:
                        await self._control_feedback(Outcome('设备控制接口暂不可用，请稍后重试。', False))

        async def _control_intent(self, text):
            async with self.control_lock:
                return await self._locked_control_intent(text)

        async def _locked_control_intent(self, text):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    text = parsed.get('content', '')
            except (ValueError, TypeError):
                pass
            command = parse_command(text)
            action = self.control_gate.route(command)
            if action in ('ignore', 'disable'):
                await self._cancel_control()
                await self._stop_output()
                if action == 'disable':
                    await self._control_feedback(Outcome('语音助手已关闭，保持待机。', speech=False))
                self._persist_control()
                return True
            if action in ('enable', 'state'):
                await self._cancel_control()
                await self._stop_output()
                text = '语音助手已开启，请说。' if self.control_gate.enabled else '语音助手处于待机。'
                await self._control_feedback(Outcome(text, speech=action == 'enable'))
                self._persist_control()
                return True
            if action == 'command':
                # Preserve a pending reboot only for its direct confirmation/cancel.
                pending = self.control_device.pending_reboot if self.control_device else None
                await self._cancel_control()
                if self.control_device and command.kind == 'reboot_confirm':
                    self.control_device.pending_reboot = pending
                await self._stop_output()
                self.control_job = asyncio.create_task(self._run_control(command, self.control_generation))
                return True
            await self._cancel_control()
            # Keep the accepted turn's identity across upstream's STT send await.
            self.control_turn.set(self.control_generation)
            self._persist_control()
            return False

        async def _control_timer(self):
            while True:
                await asyncio.sleep(1)
                async with self.control_lock:
                    if self.control_gate.expire():
                        await self._cancel_control()
                        if hasattr(self, 'websocket') and self.websocket:
                            await self._stop_output()
                            await self._control_feedback(Outcome('语音助手已自动待机。', speech=False))
                    self._persist_control()

    async def controlled_intent(conn, text):
        if isinstance(conn, HardwareConnection):
            return await conn._control_intent(text)
        return await previous_intent(conn, text)

    audio.handle_user_intent = controlled_intent
    server_module.ConnectionHandler = HardwareConnection

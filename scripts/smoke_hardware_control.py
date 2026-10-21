"""Local protocol simulator; never claims physical microphone/display validation."""
from __future__ import annotations
import asyncio
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import websockets

ROOT = Path(__file__).resolve().parents[1]


async def main(voice=False):
    report = {'scope': 'local simulated device over real server WebSocket', 'checks': [], 'audio_input': voice}
    audio_commands = {}
    if voice:
        import edge_tts
        os.environ['PATH'] = str(ROOT/'tools/native') + os.pathsep + os.environ['PATH']
        for i, text in enumerate(('打开语音助手', '当前音量是多少', '小声一点', '调低音量', '关闭语音助手')):
            path = ROOT/f'data/acceptance/control-command-{i}.mp3'
            await edge_tts.Communicate(text, 'zh-CN-XiaoxiaoNeural').save(str(path))
            audio_commands[text] = subprocess.check_output([str(ROOT/'tools/native/ffmpeg.exe'),
                '-hide_banner', '-loglevel', 'error', '-i', str(path),
                '-f', 's16le', '-ac', '1', '-ar', '16000', '-'])
    tools = [
        {'name': 'self.get_device_status', 'inputSchema': {'type': 'object', 'properties': {}}},
        {'name': 'self.audio_speaker.set_volume', 'inputSchema': {'type': 'object',
            'properties': {'volume': {'type': 'integer', 'minimum': 0, 'maximum': 100}}, 'required': ['volume']}},
        {'name': 'self.get_system_info', 'inputSchema': {'type': 'object', 'properties': {}}},
        {'name': 'self.reboot', 'inputSchema': {'type': 'object', 'properties': {}}}]
    async with websockets.connect('ws://127.0.0.1:8000/xiaozhi/v1/', additional_headers={
        'device-id': 'control-simulator', 'client-id': 'hardware-acceptance'}) as ws:
        messages = []
        calls = []
        volume = 42
        ready = asyncio.Event()
        slow = False
        delayed = []
        async def reply(payload, result, delay=0):
            if delay:
                await asyncio.sleep(delay)
            await ws.send(json.dumps({'type': 'mcp', 'payload': {
                'jsonrpc': '2.0', 'id': payload['id'], 'result': result}}))
        async def receive():
            nonlocal volume
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                event = json.loads(raw)
                messages.append(event)
                if event.get('type') != 'mcp':
                    continue
                payload = event['payload']
                method = payload.get('method')
                if method == 'initialize':
                    await reply(payload, {'serverInfo': {'name': 'simulator', 'version': '1'}})
                elif method == 'tools/list':
                    await reply(payload, {'tools': tools})
                    ready.set()
                elif method == 'tools/call':
                    name = payload['params']['name']
                    calls.append(name)
                    if name == 'self.get_device_status':
                        data = {'audio_speaker': {'volume': volume},
                            'network': {'ssid': 'Simulation WiFi', 'signal': 'strong'},
                            'battery': {'level': 75}}
                    elif name == 'self.audio_speaker.set_volume':
                        volume = payload['params']['arguments']['volume']
                        data = True
                    elif name == 'self.get_system_info':
                        data = {'application': {'version': 'test-1'}, 'chip_model_name': 'simulated'}
                    else:
                        raise AssertionError('Smoke test must never execute reboot')
                    result = {'content': [{'type': 'text', 'text': json.dumps(data)}]}
                    if slow:
                        delayed.append(asyncio.create_task(reply(payload, result, 1)))
                    else:
                        await reply(payload, result)
        pump = asyncio.create_task(receive())
        async def command(text, spoken=False):
            if spoken and text in audio_commands:
                import opuslib_next
                encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
                await ws.send(json.dumps({'type': 'listen', 'state': 'start', 'mode': 'manual'}))
                for pos in range(0, len(audio_commands[text]), 1920):
                    pcm = audio_commands[text][pos:pos+1920].ljust(1920, b'\0')
                    await ws.send(encoder.encode(pcm, 960))
                    await asyncio.sleep(.06)
                await asyncio.sleep(.3)
                await ws.send(json.dumps({'type': 'listen', 'state': 'stop', 'mode': 'manual'}))
            else:
                await ws.send(json.dumps({'type': 'listen', 'state': 'detect', 'text': text}))
        async def wait_text(text, start=0):
            began = time.monotonic()
            while time.monotonic() - began < 25:
                if any(text in str(e.get('text', '')) for e in messages[start:]):
                    return
                if pump.done():
                    await pump
                await asyncio.sleep(.05)
            raise AssertionError('Missing expected hardware text: ' + text)
        try:
            await ws.send(json.dumps({'type': 'hello', 'version': 1, 'transport': 'websocket',
                'features': {'mcp': True, 'text_stream': True},
                'audio_params': {'format': 'opus', 'sample_rate': 16000, 'channels': 1, 'frame_duration': 60}}))
            await asyncio.wait_for(ready.wait(), 20)
            await wait_text('待机')
            marker = len(messages)
            await command('你好小智')
            await command('一加一等于几')
            await asyncio.sleep(1)
            assert not any(e.get('type') in ('stt', 'text_stream') for e in messages[marker:])
            assert not calls
            report['checks'].append('default_standby_blocks_wakeup_and_chat')
            await command('打开语音助手', spoken=voice)
            await wait_text('已开启')
            for text, expected in [('当前音量是多少', '42%'), ('音量调到五十', '50%'),
                ('小声一点', '40%'), ('调低音量', '30%'), ('音量调到五十', '50%'),
                ('静音', '0%'), ('取消静音', '50%'), ('网络状态', 'Simulation WiFi'),
                ('读取设备信息', 'test-1'), ('重启设备', '十五秒'),
                ('取消重启', '已取消'), ('重新配网', '没有已验证')]:
                marker = len(messages)
                await command(text, spoken=voice and text in audio_commands)
                await wait_text(expected, marker)
                report['checks'].append(text)
            assert volume == 50
            marker = len(messages)
            await command('关闭语音助手', spoken=voice)
            await wait_text('已关闭', marker)
            marker = len(messages)
            await command('音量调到八十')
            await asyncio.sleep(.5)
            assert volume == 50
            assert not any(e.get('type') in ('stt', 'text_stream') for e in messages[marker:])
            report['checks'].append('closed_blocks_control_and_chat')
            await command('打开语音助手')
            await wait_text('已开启', marker)
            slow = True
            await command('当前音量是多少')
            await asyncio.sleep(.15)
            await command('关闭语音助手')
            await wait_text('已关闭', marker)
            await asyncio.sleep(1.3)
            tail = messages[marker:]
            closed_index = max(i for i, e in enumerate(tail) if '已关闭' in str(e.get('text', '')))
            assert not any('50%' in str(e.get('text', '')) for e in tail[closed_index + 1:])
            report['checks'].append('late_device_reply_cannot_reactivate_assistant')
        finally:
            await asyncio.gather(*delayed, return_exceptions=True)
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
    report['passed'] = True
    path = ROOT/('data/acceptance/hardware-control-voice.json' if voice else 'data/acceptance/hardware-control.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice', action='store_true', help='Feed actual Opus speech through local ASR for on/query/off')
    asyncio.run(main(parser.parse_args().voice))

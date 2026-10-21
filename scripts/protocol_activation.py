"""Acceptance clients must explicitly enable the hardware-first assistant."""
import asyncio
import json
import time


async def activate(ws):
    # Discard the initial quiet standby indication before issuing an explicit command.
    while True:
        try:
            await asyncio.wait_for(ws.recv(), .1)
        except asyncio.TimeoutError:
            break
    await ws.send(json.dumps({'type': 'listen', 'state': 'detect', 'text': '打开语音助手'}))
    enabled = False
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), deadline-time.monotonic())
        if not isinstance(raw, str):
            continue
        event = json.loads(raw)
        enabled = enabled or '已开启' in event.get('text', '')
        if enabled and event.get('type') == 'tts' and event.get('state') == 'stop':
            return
    raise TimeoutError('Assistant did not confirm explicit activation')

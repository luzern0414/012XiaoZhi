"""Exercise a real XiaoZhi server, including local ASR and decoded Opus output.

Run with the server Python environment. Makes live LLM/TTS requests.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATH'] = str(ROOT / 'tools/native') + os.pathsep + os.environ['PATH']

import edge_tts
import opuslib_next
import websockets
import urllib.request
from protocol_activation import activate


async def conversation(url: str, output: Path, audio: bytes | None = None) -> dict:
    started = time.monotonic()
    events, pcm = [], bytearray()
    frames = 0
    decoder = opuslib_next.Decoder(24000, 1)
    async with websockets.connect(url, additional_headers={
        'device-id': '02:00:00:00:00:01', 'client-id': 'local-acceptance-test',
    }, open_timeout=15, max_size=4 * 1024 * 1024) as ws:
        await ws.send(json.dumps({'type': 'hello', 'version': 1, 'transport': 'websocket',
            'audio_params': {'format': 'opus', 'sample_rate': 24000,
                             'channels': 1, 'frame_duration': 60}}))
        hello = json.loads(await asyncio.wait_for(ws.recv(), 30))
        assert hello.get('type') == 'hello', hello
        events.append(hello)
        # Provider initialization happens asynchronously after accepting a connection.
        await asyncio.sleep(3)
        await activate(ws)
        if audio is None:
            await ws.send(json.dumps({'type': 'listen', 'state': 'detect',
                'text': '请只用一句简短的中文回答，一加一等于几？'}))
        else:
            await ws.send(json.dumps({'type': 'listen', 'state': 'start', 'mode': 'manual'}))
            encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
            for pos in range(0, len(audio), 1920):
                chunk = audio[pos:pos + 1920].ljust(1920, b'\0')
                await ws.send(encoder.encode(chunk, 960))
                await asyncio.sleep(0.06)
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({'type': 'listen', 'state': 'stop', 'mode': 'manual'}))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            item = await asyncio.wait_for(ws.recv(), deadline - time.monotonic())
            if isinstance(item, bytes):
                pcm.extend(decoder.decode(item, 1440))
                frames += 1
            else:
                event = json.loads(item)
                events.append(event)
                print(json.dumps(event, ensure_ascii=False), flush=True)
                if event.get('type') == 'tts' and event.get('state') == 'stop':
                    break
        else:
            raise TimeoutError('Server did not finish the response')
    report = {'elapsed_seconds': round(time.monotonic() - started, 2),
              'opus_frames': frames, 'pcm_bytes': len(pcm), 'events': events}
    output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert any(e.get('type') == 'stt' and e.get('text') for e in events), 'No recognized input'
    if audio is not None:
        assert any(e.get('type') == 'stt' and '一加一' in e.get('text', '') for e in events), 'ASR did not recognize the spoken question'
    assert any(e.get('type') == 'tts' and e.get('state') == 'sentence_start' and e.get('text') for e in events), 'No spoken answer'
    assert frames > 0 and len(pcm) > 4800, 'No decodable speech audio'
    with wave.open(str(output.with_suffix('.wav')), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return report


async def main(args):
    folder = ROOT / 'data/acceptance'
    folder.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(args.ota, data=json.dumps({
        'application': {'version': '0.0.0'}, 'board': {'type': 'local-test'},
    }).encode(), headers={'Content-Type': 'application/json',
        'device-id': '02:00:00:00:00:01', 'client-id': 'local-acceptance-test'})
    with urllib.request.urlopen(req, timeout=15) as response:
        ota = json.load(response)
    assert ota['websocket']['url'].startswith('ws'), 'Missing OTA websocket endpoint'
    # Do not persist an auth token returned by OTA.
    summary = {'ota_websocket_url': ota['websocket']['url']}
    summary['text'] = await conversation(args.url, folder / 'text-reply')
    if not args.text_only:
        source = folder / 'spoken-question.mp3'
        await edge_tts.Communicate('请告诉我，一加一等于几？', 'zh-CN-XiaoxiaoNeural').save(str(source))
        pcm = subprocess.check_output([str(ROOT / 'tools/native/ffmpeg.exe'), '-hide_banner',
            '-loglevel', 'error', '-i', str(source), '-f', 's16le', '-ac', '1', '-ar', '16000', '-'])
        summary['voice'] = await conversation(args.url, folder / 'voice-reply', pcm)
    name = 'summary-text.json' if args.text_only else 'summary.json'
    (folder / name).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: OTA, real model replies and decoded speech' + (', local ASR' if not args.text_only else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:8000/xiaozhi/v1/')
    parser.add_argument('--ota', default='http://127.0.0.1:8003/xiaozhi/ota/')
    parser.add_argument('--text-only', action='store_true')
    asyncio.run(main(parser.parse_args()))

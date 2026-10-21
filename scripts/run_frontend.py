"""Minimal local UI with upstream audio modules preserved as copied assets."""
from __future__ import annotations
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'services/xiaozhi-esp32-server/main/digital-human'
DESTINATION = ROOT / 'data/web'

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def do_GET(self):
        if self.path in ('/health', '/api/status'):
            online = False
            configured = False
            try:
                devices = json.loads((ROOT/'data/runtime/devices.json').read_text())
                with socket.create_connection(('127.0.0.1',8000),timeout=1):
                    online = any(d.get('connected') for d in devices['devices'])
            except (OSError,ValueError,KeyError):
                pass
            try:
                iot=json.loads((ROOT/'data/runtime/iot-state.json').read_text())
                online=online or (time.time()-iot['at']<5 and any(
                    d.get('client_id')=='echoear-90e5b1d6405c' and d.get('ip')=='192.168.16.22'
                    for d in iot['devices']))
            except (OSError,ValueError,KeyError):
                pass
            configured=(ROOT/'data/runtime/hardware-ota.json').exists()
            body=json.dumps(dict(ready=True,hardware_online=online,hardware_configured=configured,model='gpt-6-luna')).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

if __name__ == '__main__':
    DESTINATION.mkdir(parents=True,exist_ok=True)
    for name in ('css','images','js','resources','wakeword_runtime'):
        shutil.copytree(SOURCE/name,DESTINATION/name,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__','logs','models'))
    shutil.copy2(SOURCE/'favicon.ico',DESTINATION/'favicon.ico')
    shutil.copytree(ROOT/'src/web',DESTINATION/'ui',dirs_exist_ok=True)
    recorder_path=DESTINATION/'js/core/audio/recorder.js'
    recorder=recorder_path.read_text(encoding='utf-8')
    before='async start() {'
    if recorder.count(before)!=1:
        raise ValueError('Upstream recorder changed; review stream ownership adapter')
    recorder=recorder.replace(before,'async start(providedStream = null) {')
    # The later availability probe has its own getUserMedia call; adapt only start().
    start=recorder.index('async start(providedStream')
    end=recorder.index('// Start visualization',start)
    segment=recorder[start:end]
    needle='const stream = await navigator.mediaDevices.getUserMedia('
    if segment.count(needle)!=1:
        raise ValueError('Upstream recorder stream acquisition changed')
    recorder=recorder[:start]+segment.replace(needle,'const stream = providedStream || await navigator.mediaDevices.getUserMedia(')+recorder[end:]
    recorder_path.write_text(recorder,encoding='utf-8')
    shutil.copy2(ROOT/'src/web/index.html',DESTINATION/'index.html')
    original=(SOURCE/'index.html').read_text(encoding='utf-8')
    (DESTINATION/'legacy.html').write_text(original.replace('127.0.0.1:8002','127.0.0.1:8003'),encoding='utf-8')
    handler=functools.partial(Handler,directory=str(DESTINATION))
    server=ThreadingHTTPServer(('127.0.0.1',8006),handler)
    def stop_monitor():
        while not (ROOT/'data/runtime/stop-web').exists():
            time.sleep(.5)
        server.shutdown()
    threading.Thread(target=stop_monitor,daemon=True).start()
    print('http://127.0.0.1:8006/',flush=True)
    server.serve_forever()

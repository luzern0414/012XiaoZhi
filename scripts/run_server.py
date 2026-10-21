"""Run unmodified upstream with file-based graceful shutdown on Windows."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'services/xiaozhi-esp32-server/main/xiaozhi-server'
RUNTIME = ROOT / 'data/runtime'


async def wait_for_stop():
    while not (RUNTIME / 'stop-server').exists():
        await asyncio.sleep(0.5)


async def no_stdin():
    await asyncio.Future()


if __name__ == '__main__':
    os.chdir(SERVER)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(SERVER))
    import app
    sys.path.insert(0, str(ROOT))
    import core.websocket_server as websocket_server
    from src.streaming import install
    install(websocket_server, RUNTIME)
    from src.hardware_control import install as install_control
    install_control(websocket_server, RUNTIME)
    from src.hardware_compat import install as install_hardware
    install_hardware(app, RUNTIME)
    from core.handle.helloHandle import wakeup_words_config
    wakeup_words_config.config_file = str(ROOT / 'data/server/wakeup_words.yaml')
    wakeup_words_config.assets_dir = str(ROOT / 'data/server/wakeup_words')
    wakeup_words_config._ensure_directories()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    state = RUNTIME / 'server.json'
    state.write_text(json.dumps({'pid': os.getpid(), 'runner': str(Path(__file__).resolve())}))
    app.monitor_stdin = no_stdin
    app.wait_for_exit = wait_for_stop
    try:
        asyncio.run(app.main())
    except KeyboardInterrupt:
        pass
    finally:
        state.unlink(missing_ok=True)

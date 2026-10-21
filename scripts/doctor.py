"""Read-only local diagnostics for the XiaoZhi development workspace."""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['PATH'] = str(ROOT / 'tools/native') + os.pathsep + os.environ['PATH']
OTA_URL = "http://113.98.195.218:10802/xiaozhi/ota/"


def command(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {exc}"


def main() -> int:
    report = {
        "workspace": str(ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "git": command("git", "--version"),
        "directories": {
            name: (ROOT / name).is_dir()
            for name in ("config", "data", "docs", "firmware", "services", "scripts", "src", "tests")
        },
    }
    # pyserial enumeration reads Windows device metadata without opening COM5.
    try:
        from serial.tools.list_ports import comports
        report["serial_ports"] = [
            {"port": item.device, "description": item.description,
             "vid": item.vid, "pid": item.pid, "hwid": item.hwid}
            for item in comports()
        ]
    except ImportError:
        report["serial_ports"] = {"error": "Run scripts/setup.ps1 to install pyserial"}
    report["tools"] = {name: command(name, flag).splitlines()[0] for name, flag in (
        ('ffmpeg', '-version'), ('ffprobe', '-version'), ('uv', '--version'))}
    report['server_python'] = command(str(ROOT / '.venv/Scripts/python.exe'), '--version')
    report['model_bytes'] = (ROOT / 'data/models/SenseVoiceSmall/model.pt').stat().st_size if (ROOT / 'data/models/SenseVoiceSmall/model.pt').exists() else 0
    report['local_services'] = {}
    for name, port, path in [('ota', 8003, '/xiaozhi/ota/'), ('web', 8006, '/health')]:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=3) as response:
                report['local_services'][name] = response.status
        except Exception as exc:
            report['local_services'][name] = {'error': str(exc)}
    try:
        with urllib.request.urlopen(OTA_URL, timeout=10) as response:
            report["ota"] = {"status": response.status, "body": response.read(300).decode("utf-8", "replace")}
    except Exception as exc:
        report["ota"] = {"error": str(exc)}
    output = ROOT / "data" / "doctor-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

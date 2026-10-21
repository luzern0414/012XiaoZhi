"""Install hash-verified Windows audio libraries and the local ASR model."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request
import zipfile

from download_asset import download

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'config/runtime-assets.lock.json').read_text())
NATIVE = ROOT / 'tools/native'
INSTALLERS = ROOT / 'tools/installers'


def valid(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == expected


def install_native():
    import imageio_ffmpeg
    import zstandard
    NATIVE.mkdir(parents=True, exist_ok=True)
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    if not valid(NATIVE / 'opus.dll', LOCK['installed_sha256']['tools/native/opus.dll']):
        archive = INSTALLERS / 'libopus.conda'
        download(LOCK['opus']['url'], archive, LOCK['opus']['sha256'])
        with zipfile.ZipFile(archive) as package:
            name = next(n for n in package.namelist() if n.startswith('pkg-') and n.endswith('.tar.zst'))
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(package.read(name))) as stream:
                with tarfile.open(fileobj=stream, mode='r|') as tar:
                    for member in tar:
                        if member.name.replace('\\', '/').endswith('/opus.dll'):
                            with tar.extractfile(member) as source:
                                (NATIVE / 'opus.dll').write_bytes(source.read())
                            break
    if not valid(NATIVE / 'ffmpeg.exe', LOCK['installed_sha256']['tools/native/ffmpeg.exe']):
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), NATIVE / 'ffmpeg.exe')
    if not valid(NATIVE / 'ffprobe.exe', LOCK['installed_sha256']['tools/native/ffprobe.exe']):
        archive = INSTALLERS / 'ffprobe.tgz'
        data = urllib.request.urlopen(LOCK['ffprobe']['url'], timeout=90).read()
        digest = base64.b64encode(hashlib.sha512(data).digest()).decode()
        if digest != LOCK['ffprobe']['sha512_integrity']:
            raise ValueError('FFprobe archive integrity mismatch')
        archive.write_bytes(data)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
            with tar.extractfile('package/ffprobe.exe') as source:
                (NATIVE / 'ffprobe.exe').write_bytes(source.read())
    for name in ('opus.dll', 'ffmpeg.exe', 'ffprobe.exe'):
        if not valid(NATIVE / name, LOCK['installed_sha256']['tools/native/' + name]):
            raise ValueError('Installed native file checksum mismatch: ' + name)
    print('Native audio libraries verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-only', action='store_true')
    parser.add_argument('--torch-only', action='store_true')
    args = parser.parse_args()
    if args.python_only:
        item = LOCK['python']
        download(item['url'], INSTALLERS / 'python-3.10.11-amd64.exe', item['sha256'])
    elif args.torch_only:
        item = LOCK['torch']
        download(item['url'], INSTALLERS / item['filename'], item['sha256'])
    else:
        install_native()
        item = LOCK['model']
        download(item['url'], ROOT / item['target'], item['sha256'])

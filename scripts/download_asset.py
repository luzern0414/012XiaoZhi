"""Download a public binary/model with resumable, validated HTTP ranges."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
from pathlib import Path
import time
import urllib.request


def download(url: str, target: Path, sha256: str | None = None, workers: int = 12):
    target.parent.mkdir(parents=True, exist_ok=True)
    if sha256 and target.is_file():
        with target.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual == sha256:
            print(f'Already verified: {target}', flush=True)
            return actual
    request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        content_range = response.headers.get("Content-Range", "")
        if response.status != 206 or not content_range.startswith("bytes 0-0/"):
            raise ValueError("Asset server does not support validated range requests")
        size = int(content_range.split("/")[-1])
        linked = response.headers.get("X-Linked-ETag", "").strip('"')
        if not sha256 and len(linked) == 64:
            sha256 = linked
    parts = target.parent / (target.name + ".parts")
    parts.mkdir(exist_ok=True)
    step = 2 * 1024 * 1024
    ranges = [(i, min(i + step, size) - 1) for i in range(0, size, step)]

    def get_range(pair):
        start, end = pair
        part = parts / str(start)
        if part.exists() and part.stat().st_size == end - start + 1:
            return part
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=50) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Unexpected Content-Range")
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError("Truncated download")
                temporary = part.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(part)
                return part
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(attempt + 1)

    print(f"Downloading {target.name}: {size / 1024 / 1024:.1f} MiB / {len(ranges)} parts", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for count, future in enumerate(concurrent.futures.as_completed([pool.submit(get_range, pair) for pair in ranges]), 1):
            future.result()
            if count % 20 == 0 or count == len(ranges):
                print(f"{target.name}: {count}/{len(ranges)} parts", flush=True)
    digest = hashlib.sha256()
    temporary = target.with_suffix(target.suffix + ".download")
    with temporary.open("wb") as output:
        for start, end in ranges:
            content = (parts / str(start)).read_bytes()
            output.write(content)
            digest.update(content)
    actual = digest.hexdigest()
    if sha256 and actual != sha256:
        raise ValueError(f"SHA256 mismatch for {target.name}: {actual}")
    temporary.replace(target)
    for part in parts.iterdir():
        part.unlink()
    parts.rmdir()
    print(f"Verified {target}: SHA256 {actual}", flush=True)
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("target", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    download(args.url, args.target, args.sha256, args.workers)

"""Recover large upstream blobs with bounded HTTP ranges on unstable links."""
from __future__ import annotations
import concurrent.futures
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_upstream import REPOS, ROOT, blob_hash

CHUNK = 512 * 1024


def download_range(job):
    url, start, end, size = job
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=30) as response:
                expected = f"bytes {start}-{end}/{size}"
                if response.status != 206 or response.headers.get("Content-Range") != expected:
                    raise ValueError("The server did not return the requested HTTP range")
                data = response.read(end - start + 2)
            if len(data) != end - start + 1:
                raise ValueError("Truncated HTTP range")
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def main():
    failures = []
    for repo, metadata, destination in REPOS:
        dest = ROOT / destination
        metadata = ROOT / metadata
        if not (metadata / ".git").exists():
            metadata = dest
        if metadata == dest:
            changes = subprocess.check_output(
                ["git", "-C", str(dest), "status", "--porcelain", "--untracked-files=no"], text=True)
            if changes.strip():
                raise SystemExit(f"Refusing to overwrite local changes in {destination}")
        commit = subprocess.check_output(["git", "-C", str(metadata), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(metadata), "ls-tree", "-rz", "HEAD"])
        for record in tree.split(b"\0"):
            if not record:
                continue
            info, name = record.split(b"\t", 1)
            mode, kind, oid = info.decode().split()
            if kind != "blob":
                continue
            name = name.decode()
            target = dest / name
            if target.exists() and blob_hash(target.read_bytes()) == oid:
                continue
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/{urllib.parse.quote(name)}"
            print(f"Recovering {name}", flush=True)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as response:
                    size = int(response.headers["Content-Length"])
                ranges = [(url, start, min(start + CHUNK, size) - 1, size) for start in range(0, size, CHUNK)]
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                    content = b"".join(pool.map(download_range, ranges))
                if blob_hash(content) != oid:
                    raise ValueError("Recovered Git blob hash mismatch")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                print(f"Verified {len(content)} bytes", flush=True)
            except Exception as exc:
                failures.append((name, str(exc)))
                print(f"Failed: {exc}", flush=True)
    print(f"Recovery failures: {len(failures)}", flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())

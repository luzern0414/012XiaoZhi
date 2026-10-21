"""Recover upstream snapshots over raw HTTPS and verify every Git blob hash."""
from __future__ import annotations

import concurrent.futures
import argparse
import hashlib
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = (
    ("78/xiaozhi-esp32", "firmware/xiaozhi-esp32-source", "firmware/xiaozhi-esp32"),
    ("xinnan-tech/xiaozhi-esp32-server", "services/xiaozhi-esp32-server-source", "services/xiaozhi-esp32-server"),
)


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def fetch(job: tuple) -> dict:
    repo, commit, dest, relative, expected = job
    target = (dest / relative).resolve()
    if not target.is_relative_to(dest.resolve()):
        raise ValueError(f"Invalid upstream path: {relative}")
    if target.is_file() and blob_hash(target.read_bytes()) == expected:
        return {"path": relative, "status": "verified"}
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{urllib.parse.quote(relative)}"
    error = ""
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "XiaoZhiWorkspace/0.1"})
            with urllib.request.urlopen(request, timeout=40) as response:
                content = response.read()
            if blob_hash(content) != expected:
                raise ValueError("Git blob hash mismatch")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return {"path": relative, "status": "verified"}
        except Exception as exc:
            error = str(exc)
            time.sleep(attempt + 1)
    return {"path": relative, "status": "failed", "error": error}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Validate local files without network requests")
    options = parser.parse_args()
    reports = []
    for repo, source, destination in REPOS:
        source_path = ROOT / source
        dest = ROOT / destination
        if not (source_path / ".git").exists():
            source_path = dest
        if not options.verify_only and source_path == dest:
            changes = subprocess.check_output(
                ["git", "-C", str(source_path), "status", "--porcelain", "--untracked-files=no"], text=True)
            if changes.strip():
                raise SystemExit(f"Refusing to overwrite local upstream changes in {destination}")
        commit = subprocess.check_output(["git", "-C", str(source_path), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(source_path), "ls-tree", "-rz", "HEAD"])
        jobs = []
        for record in tree.split(b"\0"):
            if not record:
                continue
            metadata, filename = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            if kind != "blob":
                continue
            jobs.append((repo, commit, dest, filename.decode("utf-8"), oid))
        print(f"{repo}: {len(jobs)} files at {commit}", flush=True)
        results = []
        def run(job):
            if options.verify_only:
                target = job[2] / job[3]
                valid = target.is_file() and blob_hash(target.read_bytes()) == job[4]
                return {"path": job[3], "status": "verified" if valid else "failed"}
            return fetch(job)
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                if len(results) % 100 == 0:
                    print(f"{repo}: {len(results)}/{len(jobs)} checked", flush=True)
        failures = [r for r in results if r["status"] == "failed"]
        report = {"repository": repo, "commit": commit, "destination": destination,
                  "files": len(jobs), "verified": len(jobs) - len(failures), "failures": failures}
        reports.append(report)
        (ROOT / "data" / "upstream-download-report.json").write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    lock = {"checked_date": "2026-10-19", "repositories": reports}
    lock_path = ROOT / "docs" / "02-产品与开发" / "upstream-lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(any(r["failures"] for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())

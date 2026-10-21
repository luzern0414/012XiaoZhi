"""Run a minimal streaming request using the ignored local LLM configuration."""
from __future__ import annotations
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = yaml.safe_load((ROOT / "config/local.server.yaml").read_text(encoding="utf-8"))
    name = config["selected_module"]["LLM"]
    provider = config["LLM"][name]
    base = provider.get("base_url", provider.get("url", "")).rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("This cloud smoke test requires an HTTPS provider endpoint.")
    payload = {"model": provider["model_name"],
               "messages": [{"role": "user", "content": "Reply exactly OK."}], "stream": True}
    for key in ("temperature", "max_tokens", "top_p", "frequency_penalty"):
        if provider.get(key) is not None:
            payload[key] = provider[key]
    request = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(),
                                    headers={"Authorization": "Bearer " + provider["api_key"],
                                             "Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    report = {"requested_model": provider["model_name"], "stream": True, "has_answer": False}
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            report["http_status"] = response.status
            for raw in response:
                if not raw.startswith(b"data:"):
                    continue
                value = raw[5:].strip()
                if value == b"[DONE]":
                    break
                event = json.loads(value)
                if "error" in event:
                    report["error"] = "Provider returned a stream error; details omitted to protect credentials"
                    break
                report["reported_model"] = event.get("model", report.get("reported_model"))
                for choice in event.get("choices", []):
                    if choice.get("delta", {}).get("content"):
                        report["has_answer"] = True
                    if choice.get("finish_reason"):
                        report["finish_reason"] = choice["finish_reason"]
    except urllib.error.HTTPError as exc:
        report["http_status"] = exc.code
        report["error"] = "Provider rejected the request; response body omitted"
    except Exception as exc:
        report["error"] = type(exc).__name__
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    (ROOT / "data/llm-stream-smoke-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(not report["has_answer"] or bool(report.get("error")))


if __name__ == "__main__":
    raise SystemExit(main())

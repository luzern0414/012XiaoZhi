"""Validate the native upstream overlay without printing provider secrets."""
from __future__ import annotations
import sys
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress

import yaml


def validate(config: dict) -> list[str]:
    errors = []
    server = config.get("server", {})
    url = server.get("websocket", "")
    if not isinstance(url, str) or not url.startswith(("ws://", "wss://")) or "LAN_IP" in url:
        errors.append("server.websocket must use the actual LAN IP reachable from the ESP32")
    else:
        parsed = urlsplit(url)
        host = parsed.hostname
        if not host:
            errors.append("server.websocket requires a hostname or IP address")
        elif host.lower() == "localhost":
            errors.append("server.websocket cannot advertise localhost to hardware")
        else:
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address and (address.is_loopback or address.is_unspecified):
                errors.append("server.websocket cannot advertise a loopback or wildcard address to hardware")
        if parsed.path != "/xiaozhi/v1/":
            errors.append("server.websocket must use /xiaozhi/v1/")
    for key in ("port", "http_port"):
        port = server.get(key)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(f"server.{key} must be an integer from 1 through 65535")
    selected = config.get("selected_module", {}).get("LLM")
    provider = config.get("LLM", {}).get(selected, {})
    if not provider:
        errors.append("selected_module.LLM must have a matching LLM configuration")
    elif provider.get("type") == "openai" and not provider.get("api_key"):
        errors.append("the selected LLM needs an API key in the ignored local configuration")
    return errors


def main() -> int:
    path = Path(sys.argv[1])
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("configuration must be a YAML mapping")
        errors = validate(config)
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        print(f"Invalid configuration: {exc}")
        return 1
    for error in errors:
        print(f"Configuration error: {error}")
    if not errors:
        print("Local server configuration structure is valid. Provider connectivity remains to be tested.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

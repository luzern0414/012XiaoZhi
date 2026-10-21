import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("validate_config", Path(__file__).parents[1] / "scripts/validate_config.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def config(url="ws://192.168.16.73:8000/xiaozhi/v1/"):
    return {"server": {"websocket": url, "port": 8000, "http_port": 8003},
            "selected_module": {"LLM": "Local"},
            "LLM": {"Local": {"type": "ollama", "model_name": "qwen2.5"}}}


def test_local_ollama_does_not_need_api_key():
    assert module.validate(config()) == []


@pytest.mark.parametrize("url", ["ws://127.0.0.1:8000/xiaozhi/v1/", "ws://[::1]:8000/xiaozhi/v1/", "ws://0.0.0.0:8000/xiaozhi/v1/", "ws://localhost:8000/xiaozhi/v1/", "ws://LAN_IP:8000/xiaozhi/v1/", "http://192.168.1.1/xiaozhi/v1/"])
def test_hardware_cannot_use_invalid_advertised_address(url):
    assert module.validate(config(url))


def test_cloud_provider_requires_local_secret():
    value = config()
    value["LLM"]["Local"] = {"type": "openai", "api_key": ""}
    assert any("API key" in error for error in module.validate(value))


def test_ports_must_not_be_booleans():
    value = config()
    value["server"]["port"] = True
    assert any("server.port" in error for error in module.validate(value))

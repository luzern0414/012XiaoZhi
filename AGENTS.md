# Development conventions

- This is a Windows PowerShell workspace for an ESP32 XiaoZhi voice assistant.
- Put project-owned integrations in `src/`, scripts in `scripts/`, documentation in `docs/`, committed configuration templates in `config/`.
- Put secrets only in ignored `config/local.*` files. Logs and runtime data go into ignored `logs/` and `data/`.
- `firmware/xiaozhi-esp32` and `services/xiaozhi-esp32-server` are upstream source snapshots. Preserve their licenses and follow nested AGENTS.md instructions. Prefer project-owned adapters over changing upstream.
- Current upstream Python server recommends Python 3.10 (`.venv`). Project scripts use Python 3.12 (`.venv-dev`). Avoid the system Python 3.14 for server dependencies. Native Opus and FFmpeg are additional runtime dependencies.
- USB COM5 is an ESP32-S3 device running vendor firmware 2.0.3.3. Opening the serial port caused a reset in this session. Default diagnostics must not open/reset it.
- Do not flash firmware, erase persistent storage, change board pins, or switch the hardware OTA address as part of routine project setup.
- Record upstream commits and verified file counts in `docs/02-产品与开发/upstream-lock.json`.
- Validate project-owned code with `python -m pytest tests -q`; this does not certify upstream firmware builds or hardware voice calls.
- Organize docs under `01-商务与需求/客户资料`, `01-商务与需求/方案文件`, `02-产品与开发/设计文档`, `02-产品与开发/开发记录`, `03-测试与交付/测试验收`, and `03-测试与交付/交付资料`, creating groups only when needed. Keep unmatched files (including upstream lock metadata) directly under the relevant main folder. Put images in `docs/素材/`; do not add further folder levels. Original upstream snapshots belong in `data/docs-originals/`.

# Third-party sources

- `firmware/xiaozhi-esp32`: https://github.com/78/xiaozhi-esp32, upstream MIT license retained in that repository.
- `services/xiaozhi-esp32-server`: https://github.com/xinnan-tech/xiaozhi-esp32-server, upstream MIT license retained in that repository.
- `tools/nvs`: Espressif ESP-IDF v5.5.1 `components/nvs_flash/nvs_partition_tool`, Apache-2.0; source https://github.com/espressif/esp-idf/tree/v5.5.1/components/nvs_flash/nvs_partition_tool . License retained in `tools/nvs/LICENSE`.
- The local EchoEar broker uses aMQTT 0.11.3 (MIT); greeting images use Pillow 12.0.0 (HPND). Packages are installed from PyPI and pinned in `requirements-dev.txt`.

Exact revisions and file integrity are recorded in `docs/02-产品与开发/upstream-lock.json`. Embedded dependencies and media retain their own notices and terms where provided upstream. This file does not relicense upstream materials or project-owned code.

Locally installed runtime assets are ignored by Git. Their sources and hashes are in `config/runtime-assets.lock.json`: Python (PSF), libopus (BSD-style upstream license), FFmpeg/FFprobe Windows builds (refer to each build's LGPL/GPL notices), imageio-ffmpeg (BSD-2-Clause), and SenseVoiceSmall (refer to its ModelScope model license). Preserve applicable notices and review redistribution terms before packaging binaries or avatar assets for release.

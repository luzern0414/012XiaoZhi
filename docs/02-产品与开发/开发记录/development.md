# 开发与运行指南

本机已完成独立 Python 服务端部署与真实 ASR/LLM/TTS 验收。服务端使用 Python 3.10 `.venv`，安装与诊断工具使用 Python 3.12 `.venv-dev`，不会向系统 Python 3.14 安装依赖。

## 安装

```powershell
.\scripts\setup.ps1 -InstallServerDependencies
```

脚本安装开发依赖；必要时下载校验 Python 官方安装包并验证发行者签名，安装到 `tools/python310`；创建 `.venv`；安装经过固定 SHA-256/SHA-512 校验的 Opus、FFmpeg、FFprobe 与 SenseVoiceSmall；从锁文件安装服务依赖。PyTorch 的官方文件源在本机传输缓慢，使用阿里云镜像下载同一个 wheel，哈希与官方 PyPI 元数据一致。安装需要互联网，已校验资源可以离线复用。

`config/requirements-server.lock.txt` 固定本次通过验证的 229 个包，`config/runtime-assets.lock.json` 固定二进制与模型哈希。Windows x64 是这套安装脚本验证过的平台。

## 配置

`config/local.server.yaml` 是人工维护的私密服务配置，启动时复制到上游忽略的 `main/xiaozhi-server/data/.config.yaml`。使用上游原生键名，保留模板 `config/server.example.yaml`。`LunaLLM` 配置 OpenAI 兼容 Chat Completions，实际模型名为 `gpt-6-luna`。模板不包含用户密钥。

可在 `prompt` 中定义角色与业务边界，`TTS.EdgeTTS.voice` 更换声音，`selected_module` 选择服务。当前识别在本地运行，LLM 与 EdgeTTS 使用联网服务；当前配置并非完全离线。未配置视觉、声纹和函数调用，本阶段专注语音对话。

本机同时有 WLAN、SD-WAN 和虚拟网卡。设备可用的 WLAN 地址为 `192.168.16.73`，显式写在 `server.websocket` 与 `vision_explain`。上游自动 IP 日志可能选择 SD-WAN 的 `10.10.10.156`，以配置和 OTA 实际返回值为准。DHCP 地址变化后更新本地配置并重启服务。

## 运行

```powershell
.\scripts\start-server.ps1 -Background
.\scripts\start-web.ps1
```

前台调试运行 `start-server.ps1`。后台入口会等待 OTA 就绪；Windows 通过 `scripts/run_server.py` 复用原始 `app.main()`，禁用后台标准输入监听，并以停止文件请求正常退出。`data/runtime/server.json` 记录实际服务 PID。启动重复检测，停止脚本验证 PID 归属。

网页复制上游资源和事件桥到 `data/web`，默认 OTA 改为 8003，电脑端唤醒词监听默认关闭。网页录音使用本机 Chrome/Edge；内置浏览器当前未提供可用麦克风。数字人皮肤属于测试页面可选资源，语音协议验收不依赖皮肤。

```powershell
.\scripts\stop-web.ps1
.\scripts\stop-server.ps1
```

日志位于 `logs/server/stdout.log`、`stderr.log`、`server.log`，网页日志在 `logs/web/`。后台服务随电脑关机结束，不注册开机启动任务。

## 验证

```powershell
.\.venv-dev\Scripts\python.exe scripts\doctor.py
.\.venv-dev\Scripts\python.exe scripts\validate_config.py config\local.server.yaml
.\.venv-dev\Scripts\python.exe -m pytest tests -q
uv pip check --python .venv\Scripts\python.exe
.\.venv\Scripts\python.exe scripts\smoke_voice.py
```

`smoke_voice.py` 使用合成测试问题，经过 16 kHz 单声道 Opus 输入、SenseVoice 识别、真实模型回答、TTS 和 24 kHz Opus 输出解码，要求收到正确识别文本、回答文本、非空可解码音频与结束标记。它会调用大模型和 EdgeTTS，运行数据保存在被 Git 忽略的 `data/acceptance/`。

实际 LAN 地址验证：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_voice.py --url ws://192.168.16.73:8000/xiaozhi/v1/ --ota http://192.168.16.73:8003/xiaozhi/ota/
```

协议客户端成功不等同于物理硬件通话成功。USB 默认只枚举，不打开串口；不要刷机、擦 NVS、改引脚或在例行安装中切换设备 OTA。设备接入步骤见 `hardware.md`。

## 继续开发

自有业务放 `src/`，自动化放 `scripts/`，配置模板放 `config/`。上游提供器参考 `main/xiaozhi-server/core/providers/`，函数工具参考 `plugins_func/functions/`。优先使用根目录适配器和配置，保持子模块工作树干净。完整 Java/Vue 管理后台源码已保留；本次独立 Python 服务不依赖 MySQL/Redis。

上游更新前先记录当前提交并复查兼容性。源码只读校验：`.venv-dev/Scripts/python.exe scripts/fetch_upstream.py --verify-only`。


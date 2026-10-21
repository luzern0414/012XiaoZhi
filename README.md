# XiaoZhi 本地语言助手

Windows 本地 Python 服务端已运行，复用小智开源 OTA、WebSocket 与语音链路。当前使用 **本地 SenseVoiceSmall 识别 → gpt-6-luna 联网回答 → EdgeTTS 联网合成 → Opus 音频播放**，真实音频端到端验证已通过。

## 直接使用

- 直接在硬件上使用，不需要网页。先轻点设备或用原厂唤醒词唤醒，再完整说 **“打开语音助手”** 才开始对话。**“关闭语音助手”** 立即停止回答；90 秒没有新请求自动待机。重连或服务重启后重新待机，不会主动播报招呼或告别。
- 开启后可说：“当前音量是多少”“音量调到百分之五十”“声音大一点”“小声一点”“调低音量”“静音”“取消静音”“屏幕亮度调到六十”“网络状态”“电量多少”“读取设备信息”。相对音量默认每次调整 10 个百分点。“重启设备”需要十五秒内再说“确认重启设备”。只用实际公布的接口，设置后读取状态确认。
- 原厂固件已真实公布音量、状态、亮度、系统信息和重启接口；没有公布配网、断电关机、禁用本地唤醒检测接口。关闭助手表示服务端待机，原厂本地唤醒音、屏幕亮起和麦克风检测不受此门控控制。断电后须按键或重新供电开机。
- 本机 OTA：[http://127.0.0.1:8003/xiaozhi/ota/](http://127.0.0.1:8003/xiaozhi/ota/)。
- 设备目标 OTA：`http://192.168.16.73:8003/xiaozhi/ota/`。
- 设备目标 WebSocket：`ws://192.168.16.73:8000/xiaozhi/v1/`。

**硬件已通过 USB 写入本地连接配置并联网**：EchoEar / ESP32-S3，COM5，设备 WLAN IP `192.168.16.22`，电脑 WLAN IP `192.168.16.73`。设备已真实请求本机 OTA、扩展配置并建立持续 MQTT 认证连接，网页可显示硬件在线。保留厂家 2.0.3.3 固件和屏幕音频驱动，完整 32 MB 原始备份在 `data/hardware/backup/`。已验证服务端语音链路与浏览器流式显示，实体屏幕显示及实体拾音/扬声器仍需现场确认。电脑还有 SD-WAN 网卡，上游日志可能显示 `10.10.10.156`；设备实际使用明确指定的 WLAN 地址。

## 启动与停止

双击根目录的 **`启动小智.cmd`**，检查并启动后台和设备 IoT，默认不启动网页。已运行服务会复用，设备助手保持待机。双击 **`停止小智.cmd`** 停止本机语音服务与 IoT。它不会切断硬件电源。

在项目根目录执行：

```powershell
.\scripts\start-assistant.ps1

.\scripts\stop-assistant.ps1
```

后台服务会在本次对话结束后继续运行；电脑重启后手动启动，没有添加开机自启或定时任务。前台调试可运行 `.\scripts\start-server.ps1`。日志在 `logs/server/`、`logs/iot/`。网页源码只保留为独立诊断工具，默认停止。

## 安装、验证与配置

Python 3.10、229 个服务依赖、FFmpeg、FFprobe、Opus 和约 893 MiB 的识别模型均已安装。重复执行安装会校验并复用本地资源：

```powershell
.\scripts\setup.ps1 -InstallServerDependencies
.\.venv-dev\Scripts\python.exe scripts\doctor.py
.\.venv-dev\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\smoke_hardware_control.py
```

控制验收使用模拟设备连接真实后台，测试确定性指令、开关与设备 RPC，不代表实体屏幕/拾音/扬声器验收。`smoke_voice.py` 和 `smoke_streaming.py` 会先显式开启助手，再测试真实语音/流式链路。验证记录保存在 `data/acceptance/`。密钥只在被 Git 忽略的 `config/local.server.yaml`；可修改其中的 `prompt`、模型和声音。版本锁定在 `config/requirements-server.lock.txt`，模型、原生库来源及哈希在 `config/runtime-assets.lock.json`。

## 开发目录

```text
src/         自有业务集成与扩展
scripts/     安装、启动、停止、诊断与真实链路测试
config/      配置模板、版本锁、本地私密配置
docs/        需求、开发和交付文档
data/        本地模型、运行状态、网页副本和验收产物（忽略入 Git）
logs/        服务和网页日志（忽略入 Git）
firmware/    官方 ESP32 固件子模块
services/    社区服务端子模块
tests/       自有脚本的有效回归测试
tools/       项目内 Python 与原生音频库
```

上游完整源码已经逐文件校验：[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) 1,745 个文件；[xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) 1,624 个文件。上游源码保持原样，通过根目录启动适配器复用。

参见 [开发指南](docs/02-%E4%BA%A7%E5%93%81%E4%B8%8E%E5%BC%80%E5%8F%91/%E5%BC%80%E5%8F%91%E8%AE%B0%E5%BD%95/development.md)、[运行与验收记录](docs/03-%E6%B5%8B%E8%AF%95%E4%B8%8E%E4%BA%A4%E4%BB%98/%E6%B5%8B%E8%AF%95%E9%AA%8C%E6%94%B6/2026-10-19-%E5%AE%8C%E6%95%B4%E8%AF%AD%E9%9F%B3%E6%9C%8D%E5%8A%A1%E9%AA%8C%E6%94%B6.md) 和 [调研与依赖选型](docs/02-%E4%BA%A7%E5%93%81%E4%B8%8E%E5%BC%80%E5%8F%91/%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/2026-10-19-%E6%9C%8D%E5%8A%A1%E9%83%A8%E7%BD%B2%E8%B0%83%E7%A0%94.md)。


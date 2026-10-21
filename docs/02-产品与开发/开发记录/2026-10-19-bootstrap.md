# 小智开发工程实施计划

状态补充：本文件保留最初工程准备计划。Python 3.10、模型、原生库和完整服务端语音链路现已安装并验收，最新结果见 `../03-测试与交付/2026-10-19-完整语音服务验收.md`；物理设备尚未切换本地 OTA。

目标：在当前目录复用官方固件和社区服务端，完成规范目录、可追溯源码、配置与 Windows 开发入口。

架构：ESP32-S3 负责采集/播放音频，本机 Python 服务端负责 ASR、LLM、TTS 和工具。使用上游的 WebSocket/OTA 实现，自有集成放在 `src/`。

约束：保留设备当前固件和 OTA 地址；不打开串口作为日常诊断；上游源码逐文件校验 Git blob SHA-1；密钥和运行数据不进入版本控制；服务端推荐 Python 3.10。

## 实施顺序与验收

1. 检索官方固件与服务端，并记录提交号。使用 partial clone 获取可信文件树，再通过 raw.githubusercontent.com 下载固定提交内容，Git blob 哈希不符则失败重试。验收：下载报告零失败，README、LICENSE、核心代码存在。
2. 建立 `docs/config/data/logs/scripts/src/tests/firmware/services/tools`；编写根目录 README 和 AGENTS，明确上游与自有代码边界、私密数据规则。验收：目录存在，Git 忽略密钥和运行文件。
3. 写入原生 `.config.yaml` 覆盖模板，提供 setup/start 脚本；配置验证拒绝设备不可达地址和空模型凭据。验收：模板被明确判为待填写，本地结构验证不会输出密钥。
4. 建立独立 Python 环境，验证自有诊断、下载校验和配置检查；记录尚缺模型凭据、语音模型和原生依赖。验收：本项目有效测试通过，诊断记录 OTA 与 USB 实际状态。
5. 生成调研与硬件接入指南，核实固件版本和 SDK 差异。验收：明确当前 USB 接通与网络对话验收的区别，给出下一步本地服务运行命令和设备接入地址。

## 后续运行里程碑

完成 Python 3.10 环境与 upstream requirements、FFmpeg、Opus、SenseVoiceSmall 模型安装，填写本地 LLM 配置，再运行 `scripts/start-server.ps1`。依次验收服务启动、OTA、WebSocket、ASR/LLM/TTS 测试工具，最后切换设备并实测语音对话。当前工程准备阶段不把这些尚未完成的运行验收标记为通过。

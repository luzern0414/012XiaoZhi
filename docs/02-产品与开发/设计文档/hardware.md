> 历史准备记录：本文件以下内容为切换前状态。2026-10-19 已授权写入硬件连接配置并验证联网，最新结果见 `docs/03-测试与交付/测试验收/2026-10-19-硬件联网与流式界面验收.md`。

# 硬件与本地接入

检查时间：2026-10-19，Asia/Shanghai。

## USB 观察

- 首次 Windows 串口：COM5，设备状态 OK；10:21 曾无法枚举；12:34 再次诊断已恢复 COM5，VID/PID 303A/1001。本次只枚举，没有打开串口。
- USB VID/PID：303A/1001，Espressif 原生 USB Serial/JTAG。
- 启动日志：ESP-ROM esp32s3；CPU 240MHz；16MB PSRAM；物理 Flash 探测 32MB，固件镜像头配置 16MB。
- 固件：xiaozhi 2.0.3.3，2025-11-04 编译，ESP-IDF v5.5.1。
- 具体商品板名、屏幕和音频引脚尚未确认，不能只靠芯片型号选择刷机目标。

打开串口时观察到 `rst:0x15 (USB_UART_CHIP_RESET)`。即使 DTR/RTS 为 false，当前设备仍复位，所以默认诊断只枚举 USB，不自动打开串口。原始日志保存在不入 Git 的 `data/serial-observation.log`。

日志中出现 `Invalid URL format: /GetXConfig` 和 `McpController: Failed to get xConfig response`，说明厂家固件的该功能没有拿到有效完整 URL。该错误尚不能证明它影响标准语音链路，也不能通过盲目刷官方最新固件修复。

## 网络接入

已验证远程 OTA GET：`http://113.98.195.218:10802/xiaozhi/ota/`，HTTP 200，返回“OTA接口运行正常，websocket集群数量：1”。未通过真实设备请求检查激活、绑定或 WebSocket 通话。

当前电脑 WLAN 地址：192.168.16.73。确认 ESP32 与它处于可互访网络、没有 AP 客户端隔离后，本地服务配置可使用：

```text
OTA:       http://192.168.16.73:8003/xiaozhi/ota/
WebSocket: ws://192.168.16.73:8000/xiaozhi/v1/
```

该地址可能随 DHCP 改变。先运行并验证本机服务，再修改设备配置。Windows 防火墙如提示访问权限，应仅允许实际使用的专用网络；本次没有创建防火墙规则或修改设备地址。

## 固件开发注意

已下载的官方最新固件与设备当前厂家固件并非同一版本：上游 `AGENTS.md` 要求 ESP-IDF 至少 6.0.1、推荐 6.1，设备当前使用 5.5.1。先复用已烧录固件与标准协议，不把更新上游源码等同于升级硬件。任何后续升级都先确认板型、分区、麦克风/扬声器/屏幕引脚与厂家备份。

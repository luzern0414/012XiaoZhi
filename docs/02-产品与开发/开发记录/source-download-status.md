# 上游源码与完整性

检索日期：2026-10-19。

两个仓库的完整源码工作树已下载并校验，README、许可证、核心代码与仓库内置资源均保留。版本锁定记录在本目录 `upstream-lock.json`：

- `firmware/xiaozhi-esp32/` — `78/xiaozhi-esp32`，提交 `17188094940a33c1ef5304b6ac276ae581d37a33`，1745/1745 文件通过。
- `services/xiaozhi-esp32-server/` — `xinnan-tech/xiaozhi-esp32-server`，提交 `eb9dc8ca0fc8a30bc8afb0f302dcfc1578f76a7b`，1624/1624 文件通过。

两者保留独立 Git 元数据，并通过根项目 `.gitmodules` 登记。官方 README、LICENSE、服务端 requirements、配置模板和 Docker Compose 均在原路径：

- `firmware/xiaozhi-esp32/`
- `services/xiaozhi-esp32-server/`

GitHub 普通克隆多次被网络重置，因此使用 partial clone 获取固定提交树，再通过 GitHub 官方 raw 地址逐文件下载并校验 Git blob SHA-1；大文件采用校验长度及 Content-Range 的分段下载，最终合并后再次校验哈希。复查命令：

```powershell
.\.venv-dev\Scripts\python.exe scripts\fetch_upstream.py --verify-only
git -C firmware/xiaozhi-esp32 status --short
git -C services/xiaozhi-esp32-server status --short
```

下载恢复脚本用于未修改的固定上游基线，开始修改上游后不要运行恢复命令覆盖改动；更新上游时显式选择新提交。默认只有当前浅历史，其他历史可按需 `git fetch`。

FunASR 的额外大型识别权重 `SenseVoiceSmall/model.pt` 不在上游 Git 仓库内，现已另行下载到根目录 `data/models/`，校验通过并完成完整服务端语音链路验收。物理硬件接入尚未完成，详见交付目录的完整语音服务验收记录。

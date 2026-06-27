# CLI 命令设计

## 文档目的

这份文档定义第一阶段 CLI 命令面。

CLI 是第一阶段主要入口，但 CLI 不应该承载业务逻辑。CLI 只负责解析参数、调用服务、展示结果。

## 命令命名

暂定命令名：

```text
ops
```

后续可以根据项目正式名称调整。

## 命令总览

```text
ops config init
ops config validate

ops asset scan
ops asset list
ops asset show
ops asset export
ops asset diff
ops asset import-notes

ops health check
ops health tcp-matrix
ops health http-matrix

ops diagnose internet
ops diagnose intranet
ops diagnose rdp
ops diagnose printer
ops diagnose dns
ops diagnose slow-network

ops collect local

ops task list
ops task show

ops report generate
ops export bundle
ops security check
ops security cert-check
ops automate flush-dns

ops web run
```

## config 命令

### ops config init

用途：

生成示例配置文件。

示例：

```powershell
ops config init --path ./ops.yaml
```

验收：

- 能生成默认配置。
- 不覆盖已有配置，除非显式确认。

### ops config validate

用途：

校验配置文件。

示例：

```powershell
ops config validate --config ./ops.yaml
```

验收：

- 能指出具体错误字段。
- 能显示缺失字段和非法值。

## asset 命令

### ops asset scan

用途：

执行资产发现。

示例：

```powershell
ops asset scan --profile office_lan --config ./ops.yaml
```

当目标环境禁止 ICMP，但仍希望发现开放业务端口的主机时，可以显式启用 TCP 不依赖 Ping 的模式：

```powershell
ops asset scan --profile office_lan --config ./ops.yaml --tcp-without-ping
```

说明：

- 默认模式只对 Ping 成功的主机执行 TCP 端口探测。
- `--tcp-without-ping` 会对网段内全部主机尝试配置的 TCP 端口。
- 这个模式更容易发现禁 Ping 但端口开放的 Windows 主机、服务器或网络设备。
- 代价是耗时会按“主机数 × 端口数”增长，较大网段需要谨慎使用。

验收：

- 读取 scan profile。
- 执行存活探测。
- 执行配置端口探测。
- 保存资产结果。
- 输出任务 ID。
- 启用 `--tcp-without-ping` 时，Ping 失败但 TCP 端口开放的主机也应保存为资产。

### ops asset list

用途：

查看已发现资产。

示例：

```powershell
ops asset list
```

验收：

- 能显示 IP、主机名、状态、最后发现时间。

### ops asset show

用途：

查看单个资产详情。

示例：

```powershell
ops asset show 192.168.1.10
```

验收：

- 能显示资产详情和最近探测结果。

### ops asset export

用途：

导出当前资产库中的资产清单，用于资产盘点、Excel/WPS 查看、交接或发给同事复核。

示例：

```powershell
ops asset export --config ./ops.yaml --format csv
ops asset export --config ./ops.yaml --format json --output ./reports/assets.json
```

说明：

- 默认导出 CSV，输出到配置中的 `reports.output_dir`。
- CSV 使用 `utf-8-sig`，优先保证 Windows 上 Excel 打开不乱码。
- JSON 使用结构化资产模型输出，便于后续 API、Web 或 AI 处理。
- 该命令导出当前资产库，不依赖某一次扫描任务；如果需要某次任务报告，使用 `ops report generate`。

验收：

- 支持 `csv` 和 `json`。
- 支持显式指定输出路径。
- 空资产库也能生成带表头的 CSV。
- 不支持的格式必须给出明确错误。

### ops asset diff

用途：

执行只读资产变化对比。命令会先读取历史资产库，再按指定扫描配置执行一次资产扫描，然后对比新增设备、未出现在本次扫描中的历史设备，以及历史资产记录中未出现过的新开放端口。

示例：

```powershell
ops asset diff --profile office_lan --config ./ops.yaml
ops asset diff --profile office_lan --config ./ops.yaml --tcp-without-ping
```

说明：

- 该命令只做 Ping、TCP 等只读探测。
- 不登录设备后台。
- 不修改交换机、防火墙、打印机、服务器或终端配置。
- 不自动隔离、阻断或修复任何设备。

验收：

- 能读取指定 scan profile。
- 能基于本次扫描和历史资产库识别新增资产。
- 能识别同一 profile 下本次未出现的历史资产。
- 能识别历史资产相比之前新增开放的端口。
- 能保存 `asset_diff` 任务摘要、探测结果和风险发现。
- 能通过 `ops report generate` 生成报告，并进入 `ops export bundle`。

### ops asset import-notes

用途：

从 CSV 导入资产负责人、用途、类型、描述和标签，用于把已有 Excel/WPS 资产台账里的人工信息合并到本地资产库。

示例：

```powershell
ops asset import-notes --file ./assets.csv --config ./ops.yaml
```

CSV 字段：

```csv
ip,hostname,owner,asset_type,description,tags
192.168.1.20,pc-20,Alice,workstation,财务电脑,"finance,windows"
```

说明：

- 通过 `ip` 匹配已有资产。
- 只更新资产元数据：`hostname`、`owner`、`asset_type`、`description`、`tags`。
- 空字段不会清空已有值。
- 不覆盖扫描产生的开放端口、首次发现时间、最后发现时间和来源。
- 不删除资产，不登录设备，不执行任何设备配置变更。

验收：

- 缺少 `ip` 列时给出明确错误。
- 不存在的资产行会跳过并进入任务摘要。
- 缺少 IP 的数据行会进入错误行摘要。
- 能保存 `asset_import_notes` 任务摘要。
- 能通过 `ops report generate` 生成报告，并进入 `ops export bundle`。

## health 命令

### ops health check

用途：

执行网络与服务巡检。

示例：

```powershell
ops health check --profile daily_basic --config ./ops.yaml
```

验收：

- 读取 health profile。
- 执行 Ping、DNS、TCP、HTTP 检查。
- 保存巡检结果。
- 输出异常摘要。
- 输出任务 ID。

### ops health tcp-matrix

用途：

从 CSV 批量读取 TCP 检查目标，逐行执行端口可达性测试。`name` 只是展示用，真正执行需要 `host` 和 `port`。

示例：

```powershell
ops health tcp-matrix --file ./targets.csv --config ./ops.yaml
```

CSV 字段：

```csv
name,host,port
printer,192.168.1.10,9100
nas,192.168.1.20,445
```

验收：

- 能读取 CSV 文件。
- 能逐行执行 TCP 端口检查。
- 单行失败不影响其他行。
- 能保存 `health_matrix` 任务摘要。
- 能通过 `ops report generate` 生成报告，并进入 `ops export bundle`。

### ops health http-matrix

用途：

从 CSV 批量读取 HTTP/HTTPS 检查目标，逐行执行可达性测试。`name` 只是展示用，真正执行需要 `url`。

示例：

```powershell
ops health http-matrix --file ./targets.csv --config ./ops.yaml
```

CSV 字段：

```csv
name,url,method,expected_status,owner,description
portal,https://portal.example.local,GET,200,alice,门户首页
api,https://api.example.local/health,HEAD,200-299,bob,健康检查
redirect,https://old.example.local,GET,301-302,carol,旧站跳转
```

说明：

- `method` 目前支持只读检查方法：`GET`、`HEAD`。
- 未填写 `method` 时默认使用 `GET`。
- 不支持 `POST`、`PUT`、`PATCH`、`DELETE` 等可能产生业务影响的方法。
- `expected_status` 可选，支持单个状态码（`200`）、范围（`200-299`）和多个值（`200,301,302`）。
- 未填写 `expected_status` 时不做状态码匹配检查。
- `owner` 和 `description` 为可选展示字段，不参与探测逻辑。

验收：

- 能读取 CSV 文件。
- 能逐行执行 HTTP/HTTPS 检查。
- 能按 CSV 中的 `method` 执行 `GET` 或 `HEAD`。
- 非只读 HTTP 方法必须拒绝执行。
- 能记录每行的 HTTP 状态码并与 `expected_status` 比对。
- 非法 `expected_status` 格式必须给出明确错误。
- 单行失败不影响其他行。
- 能保存 `health_matrix` 任务摘要，包含 `mismatch_count`。
- 能通过 `ops report generate` 生成报告，并进入 `ops export bundle`。

## diagnose 命令

### ops diagnose internet

用途：

诊断本机基础互联网连通性。

示例：

```powershell
ops diagnose internet --config ./ops.yaml
```

可覆盖默认目标：

```powershell
ops diagnose internet --external-ip 223.5.5.5 --dns-name www.baidu.com --http-url https://www.baidu.com
```

验收：

- 能检查外部 IP 连通性。
- 能检查 DNS 解析。
- 能检查 HTTP/HTTPS 访问。
- 能输出可能范围和下一步建议。
- 能保存任务和探测结果。

### ops diagnose intranet

用途：

诊断“内网系统打不开”的基础链路。

示例：

```powershell
ops diagnose intranet --url https://intranet.example.local --config ./ops.yaml
```

验收：

- 能解析目标 URL。
- 能检查 DNS。
- 能检查目标主机连通性。
- 能检查业务端口。
- 能检查 HTTP/HTTPS 访问。
- 能输出可能范围和下一步建议。
- 能保存任务和探测结果。

### ops diagnose rdp

用途：

诊断“远程桌面连不上”的基础链路问题。

这个命令只做 DNS、Ping、TCP 端口检查，不尝试登录，不测试账号密码，不做爆破。

示例：

```powershell
ops diagnose rdp --target 192.168.1.50 --config ./ops.yaml
ops diagnose rdp --target pc-01.example.local --config ./ops.yaml
ops diagnose rdp --target pc-01.example.local:3390 --config ./ops.yaml
ops diagnose rdp --target pc-01.example.local --port 3390 --config ./ops.yaml
```

验收：

- 目标是主机名时，先做 DNS 解析检查。
- 执行 Ping 检查。
- 执行 RDP TCP 端口检查，默认端口为 `3389`。
- 支持通过 `--port` 或 `host:port` 指定非默认端口。
- 能区分 DNS 异常、目标不可达、主机可达但 RDP 端口不可达、RDP 端口可达但 Ping 不通。
- 能保存任务和探测结果。

### ops diagnose printer

用途：

诊断“打印机不可达”或“打印机不能用”的基础链路问题。

这个命令只做 DNS、Ping、TCP 端口检查，不发送打印任务，不登录后台，不修改驱动、队列、端口或打印机配置。

示例：

```powershell
ops diagnose printer --target 192.168.1.80 --config ./ops.yaml
ops diagnose printer --target printer-01.example.local --config ./ops.yaml
ops diagnose printer --target printer-01.example.local --ports 9100,515,631 --config ./ops.yaml
```

验收：

- 目标是主机名时，先做 DNS 解析检查。
- 执行 Ping 检查。
- 执行常见打印 TCP 端口检查，默认端口为 `9100`、`515`、`631`。
- 支持通过 `--ports` 指定检查端口列表。
- 能区分 DNS 异常、目标不可达、打印机可达但常见打印端口不可达、至少一个打印端口可达、端口可达但 Ping 不通。
- 能保存任务和探测结果。

### ops diagnose dns

用途：

诊断 DNS 解析异常、解析结果不符合预期，以及解析后目标端口不可达的问题。

这个命令只做 DNS 查询和可选 TCP 端口检查，不清理 DNS 缓存，不修改网卡 DNS，不修改解析记录。

示例：

```powershell
ops diagnose dns --name intranet.example.local --config ./ops.yaml
ops diagnose dns --name intranet.example.local --expected-ip 192.168.1.10 --config ./ops.yaml
ops diagnose dns --name intranet.example.local --expected-ip 192.168.1.10 --tcp-port 443 --config ./ops.yaml
```

验收：

- 对指定域名或主机名执行系统 DNS 解析。
- 支持通过 `--expected-ip` 判断解析结果是否包含期望 IP。
- 支持通过 `--tcp-port` 对解析出的地址执行只读 TCP 端口检查。
- 能区分 DNS 解析失败、解析结果不符合预期、DNS 正常但目标端口不可达、DNS 基础检查正常。
- 能保存任务、探测结果和诊断摘要。


### ops diagnose slow-network

用途：

诊断“网络慢”的基础链路耗时问题。

这个命令只做 Ping、DNS、HTTP/HTTPS 只读检查，不修改网卡、DNS、代理、路由或设备配置。

示例：

```powershell
ops diagnose slow-network --config ./ops.yaml
ops diagnose slow-network --external-ip 223.5.5.5 --dns-name www.baidu.com --http-url https://www.baidu.com --config ./ops.yaml
```

验收：

- 执行外部 IP Ping 检查并记录耗时。
- 执行 DNS 解析检查并记录耗时。
- 执行 HTTP/HTTPS 检查并记录耗时。
- 能区分基础链路不可达、DNS 异常、HTTP 异常、DNS 耗时偏高、基础网络延迟偏高、HTTP 响应耗时偏高、基础延迟检查正常。
- 能保存任务和探测结果。

## collect 命令

### ops collect local

用途：

采集本机系统与网络排障上下文，用于现场排障、交接和诊断包留档。

第一阶段只做只读采集，不执行修复，不扫描网段。

示例：

```powershell
ops collect local --config ./ops.yaml
```

当前采集内容：

- 主机名、FQDN、当前用户、操作系统信息。
- 网卡名称、状态、IPv4、IPv6、默认网关、DNS。
- 默认路由摘要。
- 代理环境变量、Windows Internet Settings、WinHTTP 代理摘要。

验收：

- 能保存 `ops_collect` 任务。
- 能保存本机信息快照。
- 能在 `ops task show` 中查看快照摘要。
- 能通过 `ops report generate` 生成报告。
- 能进入 `ops export bundle` 诊断包。
- 代理 URL 中的用户名和密码必须脱敏。

## task 命令

### ops task list

用途：

查看任务历史。

示例：

```powershell
ops task list
```

验收：

- 显示任务 ID、类型、状态、开始时间、结束时间。

### ops task show

用途：

查看任务详情。

示例：

```powershell
ops task show task-001
```

验收：

- 显示任务状态、目标、结果摘要、错误摘要。

## report 命令

### ops report generate

用途：

基于任务生成报告。

示例：

```powershell
ops report generate --task task-001 --format markdown
```

验收：

- 能读取任务结果。
- 能生成 Markdown 报告。
- 能输出报告路径。

## export 命令

### ops export bundle

用途：

导出诊断包，便于交接、留档或发给同事分析。

示例：

```powershell
ops export bundle --config ./ops.yaml
ops export bundle --config ./ops.yaml --task task-001
ops export bundle --config ./ops.yaml --task task-001 --output ./bundles/task-001.zip
```

验收：

- 能输出 zip 文件。
- zip 中包含配置摘要、任务、资产、探测结果和摘要文档。
- 不直接打包完整原始配置，降低敏感信息泄露风险。

## security 命令

### ops security check

用途：

基于已发现资产执行轻量安全检查。

示例：

```powershell
ops security check --config ./ops.yaml
```

验收：

- 能读取已发现资产。
- 能基于配置中的高风险端口生成风险发现。
- 能保存安全检查任务。
- 能输出风险等级、标题和建议。
- 不执行漏洞利用或密码测试。

### ops security cert-check

用途：

只读检查 HTTPS/TLS 服务证书是否过期或即将过期。

示例：

```powershell
ops security cert-check --target intranet.example.local --config ./ops.yaml
ops security cert-check --target intranet.example.local:8443 --warning-days 14 --config ./ops.yaml
ops security cert-check --target https://intranet.example.local --config ./ops.yaml
```

验收：

- 支持 `https://` URL、主机名和 `host:port`。
- 执行 TCP/TLS 握手并读取服务端证书。
- 输出证书剩余天数和风险发现。
- 已过期证书标记为高风险，即将过期证书标记为中风险。
- 不修改证书、不登录服务器、不重载服务。

## automate 命令

### ops automate flush-dns

用途：

清理本机 DNS 缓存。该命令属于低风险变更，默认只执行 dry-run，必须显式 `--confirm` 才会调用本机系统命令执行清理。

示例：

```powershell
ops automate flush-dns --config ./ops.yaml --dry-run
ops automate flush-dns --config ./ops.yaml --confirm
```

说明：

- 默认不执行变更；未传 `--confirm` 时按 dry-run 处理。
- `--dry-run` 只生成计划和任务记录。
- `--confirm` 才执行本机 DNS 缓存清理。
- 仅支持本机，不支持远程机器或批量执行。
- 不修改 DNS 服务器配置，不修改网卡配置，不重启服务。

验收：

- dry-run 能保存 `automation` 任务，风险等级为 `low_change`。
- confirm 能保存执行结果、返回码、耗时和错误摘要。
- 同时传 `--dry-run` 和 `--confirm` 必须报错。
- 能通过 `ops report generate` 生成报告，并进入 `ops export bundle`。

## web 命令

### ops web run

用途：

启动 Web Console 服务（FastAPI + Uvicorn），在浏览器中查看资产、任务、报告和巡检结果。

示例：

```powershell
ops web run --config ./ops.yaml
ops web run --host 0.0.0.0 --port 3000
ops web run --reload
```

说明：

- 默认监听 `127.0.0.1:8080`，通过 `--host` 和 `--port` 调整。
- `--reload` 启用开发热重载。
- Web Console 只读调用 `SQLiteStore`，不直接调用 Adapter。
- 启动后访问 `http://host:port` 查看仪表盘，`http://host:port/docs` 查看 API 文档。
- 需要安装 Web 依赖：`pip install 'it-ops-toolkit[web]'`。

验收：

- 能正常启动并监听指定端口。
- 仪表盘能展示资产、任务、报告和概览统计。
- API 端点返回正确数据。
- 缺少 Web 依赖时给出明确提示。

## 全局参数

建议支持：

```text
--config
--output
--format
--verbose
--quiet
--json
```

## 输出原则

默认输出给人看。

加 `--json` 时输出结构化 JSON，方便脚本调用。

CLI 输出不应该替代数据存储和报告模块。

## 第一阶段最小命令

如果需要进一步压缩第一版，最少保留：

```text
ops config init
ops asset scan
ops health check
ops task list
ops report generate
```

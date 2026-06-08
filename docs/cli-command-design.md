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

ops health check

ops diagnose internet
ops diagnose intranet
ops diagnose rdp

ops collect local

ops task list
ops task show

ops report generate
ops export bundle
ops security check
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

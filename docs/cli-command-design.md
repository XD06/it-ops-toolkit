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

ops health check

ops diagnose internet

ops task list
ops task show

ops report generate
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

验收：

- 读取 scan profile。
- 执行存活探测。
- 执行配置端口探测。
- 保存资产结果。
- 输出任务 ID。

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

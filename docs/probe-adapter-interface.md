# Probe 与 Adapter 接口设计

## 文档目的

这份文档定义第一阶段 Probe / Adapter 的输入输出结构。

Probe 是具体探测能力。Adapter 是封装外部协议、命令或工具的适配器。

第一阶段先实现：

- Ping Probe。
- DNS Probe。
- TCP Probe。
- HTTP Probe。

## 设计原则

- 业务模块不直接调用系统命令。
- 所有 Probe 输出统一结构。
- 单个 Probe 失败不导致整个任务崩溃。
- 错误必须可诊断。
- 敏感信息不能进入日志和报告。

## ProbeRequest

ProbeRequest 是 Probe 的统一请求结构。

字段：

| 字段 | 说明 |
|---|---|
| `request_id` | 请求 ID |
| `task_id` | 所属任务 |
| `probe_type` | `ping`、`dns`、`tcp`、`http` |
| `target` | 目标对象 |
| `options` | Probe 参数 |
| `timeout_ms` | 超时时间 |
| `retries` | 重试次数 |

示例：

```json
{
  "request_id": "probe-001",
  "task_id": "task-001",
  "probe_type": "tcp",
  "target": {
    "type": "ip",
    "value": "192.168.1.10"
  },
  "options": {
    "port": 3389
  },
  "timeout_ms": 3000,
  "retries": 1
}
```

## ProbeResult

ProbeResult 是 Probe 的统一响应结构。

字段：

| 字段 | 说明 |
|---|---|
| `id` | 结果 ID |
| `request_id` | 请求 ID |
| `task_id` | 所属任务 |
| `probe_type` | Probe 类型 |
| `target` | 目标 |
| `status` | `success`、`failed`、`timeout`、`skipped` |
| `started_at` | 开始时间 |
| `ended_at` | 结束时间 |
| `duration_ms` | 耗时 |
| `observations` | 观察值 |
| `error` | 错误对象 |
| `evidence` | 证据 |

示例：

```json
{
  "id": "result-001",
  "request_id": "probe-001",
  "task_id": "task-001",
  "probe_type": "tcp",
  "target": {
    "type": "ip",
    "value": "192.168.1.10"
  },
  "status": "success",
  "duration_ms": 23,
  "observations": {
    "port": 3389,
    "open": true
  },
  "error": null,
  "evidence": {
    "summary": "TCP 3389 connected"
  }
}
```

## Ping Probe

输入：

- IP 或 hostname。
- 超时。
- 重试次数。

输出观察值：

- 是否可达。
- 平均延迟。
- 丢包情况。
- 原始摘要。

## DNS Probe

输入：

- hostname。
- DNS 服务器，可选。
- 记录类型，默认 A。

输出观察值：

- 解析结果。
- 解析耗时。
- DNS 服务器。
- 失败原因。

## TCP Probe

输入：

- IP 或 hostname。
- 端口。
- 超时。

输出观察值：

- 端口是否开放。
- 连接耗时。
- 失败原因。

## HTTP Probe

输入：

- URL。
- 方法，默认 GET。
- 超时。
- 是否检查证书。

输出观察值：

- 状态码。
- 响应时间。
- 是否可访问。
- 证书到期时间，可选。
- 重定向信息，可选。

## 错误代码建议

| 错误代码 | 含义 |
|---|---|
| `timeout` | 超时 |
| `dns_failed` | DNS 解析失败 |
| `connection_refused` | 连接被拒绝 |
| `network_unreachable` | 网络不可达 |
| `invalid_target` | 目标格式错误 |
| `adapter_error` | Adapter 内部错误 |
| `permission_denied` | 权限不足 |

## Adapter 边界

Adapter 负责：

- 调用外部能力。
- 捕获原始错误。
- 归一化结果。
- 脱敏。

Adapter 不负责：

- 判断业务风险。
- 生成报告。
- 直接保存数据库。
- 发送通知。

## 第一阶段验收标准

- Ping、DNS、TCP、HTTP 都实现统一接口。
- 每个 Probe 都有错误处理。
- ProbeResult 可被报告模块直接消费。
- 业务模块不直接调用外部命令。


# 配置文件设计

## 文档目的

这份文档定义第一阶段配置文件的建议结构。

配置中心的目标是避免把网段、目标、端口、超时、报告路径等信息写死在代码或脚本里。

## 格式建议

第一阶段建议优先使用 YAML。

原因：

- 对运维人员可读性较好。
- 支持注释。
- 适合配置层级。
- 比 JSON 更适合人工编辑。

该选择已记录在 `docs/adr/0004-phase-1-yaml-config.md`。

## 示例配置

```yaml
app:
  name: IT Ops Toolkit
  environment: local

scan_profiles:
  office_lan:
    description: 办公网段基础扫描
    subnets:
      - 192.168.1.0/24
    ping:
      enabled: true
      timeout_ms: 1000
      retries: 1
    tcp_ports:
      - 22
      - 80
      - 443
      - 445
      - 3389

health_profiles:
  daily_basic:
    description: 每日基础巡检
    targets:
      - name: 默认网关
        type: ip
        value: 192.168.1.1
        checks:
          - ping
      - name: 内部 DNS
        type: ip
        value: 192.168.1.2
        checks:
          - ping
          - dns
      - name: 内网业务系统
        type: url
        value: https://intranet.example.local
        checks:
          - http

probe_defaults:
  timeout_ms: 1000
  retries: 1
  concurrency: 32

reports:
  output_dir: ./reports
  formats:
    - markdown
    - csv

storage:
  type: local
  path: ./data

security:
  risky_ports:
    - 22
    - 445
    - 1433
    - 3306
    - 3389
    - 6379
```

## 配置分区说明

### app

平台基础信息。

### scan_profiles

资产扫描配置。

一个 scan profile 可以包含多个网段和端口策略。

### health_profiles

巡检配置。

一个 health profile 可以包含多个目标，每个目标可以定义检查类型。

### probe_defaults

Probe 默认参数。

包括超时、重试、并发等。

### reports

报告输出配置。

### storage

本地存储配置。

第一阶段建议先使用本地目录或轻量数据库。

### security

安全检查相关配置。

第一阶段主要用于高风险端口提示。

## 校验规则

配置中心至少需要校验：

- 网段格式是否合法。
- 目标类型是否合法。
- URL 是否合法。
- 端口是否在 1-65535。
- 超时是否为正数。
- 输出目录是否可创建。
- storage 类型是否支持。

## 敏感信息规则

第一阶段不建议在配置文件中直接保存明文密码。

如果后续需要凭据，应使用引用：

```yaml
credentials:
  network_device_readonly:
    ref: env:NETWORK_DEVICE_READONLY
```

日志和报告不得输出凭据值。

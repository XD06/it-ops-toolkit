# AI 运维助手模块

## 模块职责

AI 运维助手负责基于结构化结果、报告和知识库内容进行解释、总结、建议和文档生成。

它的定位是 Copilot，不是默认自动执行者。

## 现实场景

中小企业运维经常需要把技术信息翻译成不同读者能理解的内容：

- 给自己看：详细证据和排查步骤。
- 给领导看：影响范围、原因、恢复情况、后续措施。
- 给业务部门看：当前状态和预计处理动作。
- 给新人看：下一步应该查什么。

AI 适合做这类表达、总结和建议工作。

## 不负责什么

本模块不负责：

- 直接执行高风险命令。
- 替代确定性业务规则。
- 保存主数据。
- 绕过权限。
- 处理未经脱敏的敏感信息。

关键判断应该优先写在业务模块中，AI 负责解释和辅助。

## 输入

输入可以包括：

- 结构化巡检结果（`ProbeResult`）。
- 诊断结果（`DiagnosisResult` + `Finding`）。
- 安全发现。
- 报告内容。
- 知识库条目。
- 用户问题。
- 输出风格要求。

## 输出

输出可以包括：

- 巡检总结。
- 异常解释。
- 排障建议。
- 日报或周报草稿。
- 故障复盘草稿。
- SOP 匹配结果。
- 需要人工确认的问题。

## 依赖模块

依赖：

- 数据存储。
- 报告中心。
- 知识库。
- 权限与审计。
- 日志与观测性。

被依赖：

- Web Console。
- CLI。
- Agent Runner。

## 架构设计（Phase 7）

### AI Adapter 模式

AI 调用封装成 `AIAdapter` 接口，领域服务不依赖具体 AI 实现。

```
领域服务（summarize, explain, recommend）
    ↓ 调用
AIAdapter（接口）
    ↓ 实现
├── OpenAIAdapter    → OpenAI API（gpt-4o / gpt-4o-mini）
├── OllamaAdapter    → 本地模型（Ollama REST API）
└── TemplateAdapter  → 规则模板引擎（零成本兜底）
```

详细架构决策见 ADR-0007。

### 数据模型

**AIInput**：发送给 AI 的结构化数据。

```python
class AIInput(BaseModel):
    task: TaskRun              # 任务上下文
    results: list[ProbeResult] # 探测结果
    findings: list[Finding]    # 诊断发现
    assets: list[Asset]        # 相关资产（可选）
    context: dict              # 额外上下文（可选）
```

**AIOutput**：AI 返回的结构化结果。

```python
class AIOutput(BaseModel):
    summary: str                    # 一句话摘要
    facts: list[str]                # 已确认事实（来自结构化数据）
    inferences: list[str]           # 推断（AI 推理得出，需标注）
    recommendations: list[str]      # 建议
    needs_human_review: bool        # 是否需要人工确认
    confidence: float               # 置信度 0-1
    sources: list[str]              # 引用的结果 ID 或知识库条目
```

关键设计：`facts` 和 `inferences` 严格分离。`facts` 只能来自结构化数据，`inferences` 是 AI 推理，必须标注。

### 配置

```yaml
ai:
  backend: "openai"        # openai | ollama | template
  openai:
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-4o-mini"
    base_url: null          # 可选自定义 endpoint
  ollama:
    host: "http://localhost:11434"
    model: "qwen2.5:7b"
  template:
    rules_dir: "config/ai-templates"
```

### 脱敏处理

AI 输入在发送前必须经过 `sanitize_ai_input()` 处理：

- 代理 URL 中的凭据替换为 `***`。
- 移除所有 `password`、`token`、`secret`、`api_key` 字段。
- 系统信息中的用户名替换为 `***`。

## Phase 7 实施计划

### 第一步：AI 报告摘要 ✅

**价值**：最高性价比，风险最低。把结构化 `ProbeResult` + `Finding` 转成人类可读摘要。

**实现**：
1. ✅ 定义 `AIInput` 和 `AIOutput` 数据模型（`models.py`）。
2. ✅ 实现 `AIAdapter` 接口（`ai_copilot.py`）。
3. ✅ 实现 `TemplateAdapter`（零成本兜底，基于规则模板生成摘要）。
4. ✅ 实现 `OpenAIAdapter`（可选依赖 `openai`）。
5. ✅ 实现 `OllamaAdapter`（可选依赖 `httpx`）。
6. ✅ 实现领域服务 `summarize_task(task_id) -> AIOutput`。
7. ✅ CLI 新增 `ops ai summarize --task <task_id>`。
8. ✅ Web Console 新增 AI API 端点。

**TemplateAdapter 示例输出**：
```json
{
  "summary": "巡检完成，3 个目标正常，1 个安全发现需关注",
  "facts": [
    "网关 192.168.1.1 可达，平均延迟 5ms，无丢包",
    "DNS 解析 www.example.com 正常，耗时 12ms",
    "192.168.1.50 的 445 端口处于开放状态"
  ],
  "inferences": [],
  "recommendations": [
    "建议在防火墙限制 192.168.1.50 的 445 端口访问来源"
  ],
  "needs_human_review": true,
  "confidence": 1.0,
  "sources": ["result-001", "result-002", "finding-001"]
}
```

### 第二步：AI 异常解释 ✅

**价值**：自然语言交互，降低使用门槛。

**实现**：
1. ✅ `ops ai explain` 命令，支持 `--question` 自然语言提问。
2. ✅ AI 基于结构化异常数据做解释。
3. ✅ AI 只做结果解释，实际探测由确定性代码执行。
4. ✅ AI 不能自己调用 `ping` 或 `nslookup`。

### 第三步：AI 周报 ✅

**价值**：自动汇总一段时间的巡检结果。

**实现**：
1. ✅ `ops ai weekly --days N` 命令。
2. ✅ 汇总指定天数的探测结果和发现。

### 第四步：SOP 匹配

**价值**：诊断发现问题时，AI 自动匹配相关 SOP。

**状态**：待实现。需要知识库模块支持。

## 风险控制

AI 输出必须区分：

- 已确认事实（`facts`）：只能来自结构化数据。
- 基于证据的推断（`inferences`）：AI 推理得出，需标注。
- 建议动作（`recommendations`）：下一步建议。
- 需要人工确认的事项（`needs_human_review`）。

AI 不应直接看到：

- 明文密码。
- Token。
- 私钥。
- 不必要的个人信息。
- 未脱敏日志。

AI 安全规则：
- AI 不能自己调用 Adapter（ping、dns 等）。
- AI 不能默认执行高风险动作。
- AI 输出中 `inferences` 不能伪装成 `facts`。
- AI 输出中 `confidence < 0.7` 时自动设置 `needs_human_review = true`。
- AI 调用失败时降级为 TemplateAdapter 输出。
- AI 调用有超时限制（默认 30 秒）。
- AI 调用必须记录审计日志（调用时间、后端、耗时、是否成功）。

## 验收标准

Phase 7 完成时，应满足：

- ✅ AI 能引用结构化结果。
- ✅ AI 输出能区分事实、推断和建议。
- ✅ AI 不默认执行高风险动作。
- ✅ AI 后端可切换（OpenAI / Ollama / Template）。
- ✅ AI 输入不包含敏感信息。
- ✅ TemplateAdapter 作为默认兜底，不依赖任何外部服务。
- ✅ OpenAI 和 Ollama 适配器是可选依赖，核心包不强依赖。
- ✅ AI 调用有审计日志。

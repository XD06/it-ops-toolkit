# ADR 0007：AI 集成策略——Copilot 模式与 Adapter 解耦

## 状态

已接受，作为 Phase 7（AI 运维助手）的架构方向。

## 背景

Phase 1-4 已完成，平台沉淀了大量结构化运维数据（ProbeResult、Finding、TaskRun、Asset）。这些数据是 AI 的理想输入：

- 结构化：AI 不需要从非结构化文本中提取信息。
- 有证据链：Finding 包含严重程度、描述和建议，AI 可以引用。
- 有上下文：TaskRun 关联了任务类型、目标、时间，AI 可以理解执行场景。

但 AI 集成面临三个关键问题：

1. **后端选择**：不同中小企业的环境不同——有的可以访问外网用 OpenAI API，有的要求数据不出内网用本地模型，有的只是想要简单的规则摘要。
2. **安全边界**：AI 不能默认执行高风险动作，不能看到明文凭据，不能把推断伪装成确定结论。
3. **成本控制**：AI 调用有费用（API）或资源开销（本地模型），不能无限制调用。

## 决策

### 1. AI 定位：Copilot，不是自动执行者

AI 消费结构化数据做解释、总结和建议。AI 不替代确定性业务规则，不默认执行高风险动作。

AI 的四个职责：
- **解释**：把结构化 ProbeResult 翻译成人类可读描述。
- **总结**：从多个结果中提取关键信息。
- **建议**：基于 Finding 和知识库给出下一步建议。
- **匹配**：从知识库中匹配相关 SOP。

### 2. AI Adapter 模式

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

配置切换：
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

### 3. AIInput / AIOutput 数据模型

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

### 4. AI 安全规则

- AI 输入不包含明文密码、Token、私钥。
- AI 输入中的代理 URL 已脱敏（凭据替换为 `***`）。
- AI 不能自己调用 Adapter（ping、dns 等）。
- AI 不能默认执行高风险动作。
- AI 输出中 `inferences` 不能伪装成 `facts`。
- AI 输出中 `confidence < 0.7` 时自动设置 `needs_human_review = true`。
- AI 调用失败时降级为 TemplateAdapter 输出。
- AI 调用有超时限制（默认 30 秒）。

### 5. 分阶段落地

| 步骤 | 能力 | 输入 | 输出 | 风险 |
|---|---|---|---|---|
| 第一步 | AI 报告摘要 | TaskRun + ProbeResult + Finding | AIOutput | 最低 |
| 第二步 | AI 诊断助手 | 自然语言 + 诊断结果 | 解释 + 建议 | 低 |
| 第三步 | AI 周报 | 一周 TaskRun + Finding | 管理层/技术版报告 | 低 |
| 第四步 | SOP 匹配 | Finding + 知识库 | 相关 SOP 引用 | 低 |

第一步优先实现，因为：
- 输入完全来自已有结构化数据，不需要额外采集。
- 输出是只读的摘要，不涉及任何执行动作。
- 价值最直观：把"一堆表格"变成"一段人话"。

## 备选方案

### 方案 B：直接调用 OpenAI API，不做 Adapter 解耦

优点：
- 实现最简单。
- 效果最好。

缺点：
- 强依赖外网和 OpenAI 服务。
- 内网环境无法使用。
- 未来切换模型需要改业务代码。

### 方案 C：只做规则模板引擎，不接 AI

优点：
- 零成本、零风险。
- 完全可控。

缺点：
- 无法处理复杂场景的解释。
- 无法生成自然语言建议。
- 价值有限。

### 方案 D：AI 直接执行运维动作

优点：
- 全自动化。

缺点：
- 安全风险极高。
- 不可审计。
- 不符合项目"AI 是受控助手"的定位。

## 后果

正面影响：
- AI 后端可切换，适应不同企业环境。
- 领域服务不依赖具体 AI 实现，可独立测试。
- AI 输出结构化，可被 Web Console 和 CLI 统一消费。
- TemplateAdapter 作为兜底，即使没有 AI 也能输出基本摘要。

负面影响：
- 需要维护多个 AIAdapter 实现。
- AI 调用有延迟，需要异步处理。
- 本地模型需要硬件资源（GPU 或大内存）。
- Prompt 工程需要持续优化。

## 执行要求

- AIAdapter 接口定义在 `src/it_ops_toolkit/ai_adapter.py`。
- AI 输入必须经过脱敏处理（`sanitize_ai_input()` 函数）。
- AI 输出必须经过结构化验证（Pydantic 模型校验）。
- AI 调用必须记录审计日志（调用时间、后端、耗时、是否成功）。
- TemplateAdapter 作为默认兜底实现，不依赖任何外部服务。
- OpenAI 和 Ollama 适配器是可选依赖，核心包不强依赖。

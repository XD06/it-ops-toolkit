"""AI 运维助手模块。

架构遵循 ADR-0007：
- AI 是 Copilot，不是自动执行者。
- AIAdapter 接口解耦具体实现。
- TemplateAdapter 作为零成本兜底。
- OpenAI / Ollama 是可选依赖。
- AI 输入必须脱敏，输出区分 facts / inferences。
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from .config import AIConfig, OpsConfig
from .models import (
    AIInput,
    AIOutput,
    AICallLog,
    Asset,
    Finding,
    ProbeResult,
    ProbeStatus,
    Severity,
    TaskRun,
    TaskStatus,
)
from .storage import SQLiteStore, TaskRecordNotFound


class AIAdapterError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 脱敏处理
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "credential",
    "auth",
}


def sanitize_ai_input(data: dict[str, Any]) -> dict[str, Any]:
    """递归脱敏 AI 输入数据。

    - 移除敏感字段（password / token / secret / api_key 等）。
    - 代理 URL 中的凭据替换为 ***。
    """
    return _sanitize_recursive(data)


def _sanitize_recursive(data: Any) -> Any:
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key.lower() in _SENSITIVE_KEYS:
                result[key] = "***"
            elif key.lower() == "proxy" and isinstance(value, dict):
                result[key] = _sanitize_proxy(value)
            else:
                result[key] = _sanitize_recursive(value)
        return result
    if isinstance(data, list):
        return [_sanitize_recursive(item) for item in data]
    if isinstance(data, str):
        return _sanitize_url_in_string(data)
    return data


def _sanitize_proxy(proxy: dict[str, Any]) -> dict[str, Any]:
    """脱敏代理配置。"""
    result = dict(proxy)
    for key in ("username", "password", "user", "pass"):
        if key in result:
            result[key] = "***"
    return result


def _sanitize_url_in_string(text: str) -> str:
    """脱敏 URL 中的用户名密码（http://user:pass@host → http://***:***@host）。"""
    import re

    return re.sub(
        r"(https?://)[^:@/\s]+:[^@/\s]+@",
        r"\1***:***@",
        text,
    )


# ---------------------------------------------------------------------------
# AIAdapter 接口
# ---------------------------------------------------------------------------


class AIAdapter(ABC):
    """AI 适配器接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """适配器名称。"""

    @abstractmethod
    def generate(self, ai_input: AIInput, *, prompt: str | None = None) -> AIOutput:
        """根据输入生成 AI 输出。

        Args:
            ai_input: 脱敏后的结构化输入。
            prompt: 可选的自定义提示词。

        Returns:
            结构化 AI 输出。
        """


# ---------------------------------------------------------------------------
# TemplateAdapter — 零成本兜底实现
# ---------------------------------------------------------------------------


class TemplateAdapter(AIAdapter):
    """基于规则的模板引擎，零外部依赖。

    根据结构化数据按规则生成摘要，不调用任何外部 AI 服务。
    适合没有 AI API 的环境，或作为 AI 调用失败时的降级方案。
    """

    @property
    def name(self) -> str:
        return "template"

    def generate(self, ai_input: AIInput, *, prompt: str | None = None) -> AIOutput:
        start = time.monotonic()

        results = ai_input.results
        findings = ai_input.findings

        # 统计
        total = len(results)
        success_count = sum(1 for r in results if r.status == ProbeStatus.success)
        failed_count = sum(1 for r in results if r.status == ProbeStatus.failed)
        timeout_count = sum(1 for r in results if r.status == ProbeStatus.timeout)

        # 事实列表
        facts: list[str] = []
        sources: list[str] = []

        for r in results:
            fact = self._result_to_fact(r)
            if fact:
                facts.append(fact)
                sources.append(r.id)

        for f in findings:
            facts.append(f"[{f.severity.value.upper()}] {f.title}: {f.description}")
            sources.append(f.id)

        # 摘要
        parts: list[str] = []
        if total > 0:
            parts.append(f"巡检 {total} 个目标")
            if success_count:
                parts.append(f"{success_count} 个正常")
            if failed_count:
                parts.append(f"{failed_count} 个失败")
            if timeout_count:
                parts.append(f"{timeout_count} 个超时")
        else:
            parts.append("无探测结果")

        if findings:
            critical = sum(1 for f in findings if f.severity == Severity.critical)
            high = sum(1 for f in findings if f.severity == Severity.high)
            if critical:
                parts.append(f"{critical} 个严重发现")
            if high:
                parts.append(f"{high} 个高危发现")

        summary = "，".join(parts) + "。"

        # 建议
        recommendations: list[str] = []
        for f in findings:
            if f.recommendation:
                recommendations.append(f.recommendation)

        # 推断（模板引擎不做推断）
        inferences: list[str] = []

        # 是否需要人工确认
        needs_review = bool(findings) or failed_count > 0 or timeout_count > 0

        duration_ms = int((time.monotonic() - start) * 1000)

        return AIOutput(
            summary=summary,
            facts=facts,
            inferences=inferences,
            recommendations=recommendations,
            needs_human_review=needs_review,
            confidence=1.0,
            sources=sources,
            backend=self.name,
            duration_ms=duration_ms,
        )

    def _result_to_fact(self, result: ProbeResult) -> str | None:
        """把单条探测结果转成事实描述。"""
        target_val = result.target.value
        status_text = {
            ProbeStatus.success: "正常",
            ProbeStatus.failed: "失败",
            ProbeStatus.timeout: "超时",
            ProbeStatus.skipped: "跳过",
        }.get(result.status, str(result.status))

        if result.probe_type == "ping":
            avg_rtt = result.observations.get("avg_rtt_ms")
            loss = result.observations.get("packet_loss_percent")
            if result.status == ProbeStatus.success and avg_rtt is not None:
                loss_text = f"，丢包率 {loss}%" if loss is not None else ""
                return f"Ping {target_val} {status_text}，平均延迟 {avg_rtt}ms{loss_text}"
            return f"Ping {target_val} {status_text}"

        if result.probe_type == "dns":
            duration = result.observations.get("duration_ms")
            resolved = result.observations.get("resolved_addresses", [])
            if result.status == ProbeStatus.success:
                resolved_text = f"，解析到 {','.join(resolved[:3])}" if resolved else ""
                duration_text = f"，耗时 {duration}ms" if duration is not None else ""
                return f"DNS 解析 {target_val} {status_text}{resolved_text}{duration_text}"
            return f"DNS 解析 {target_val} {status_text}"

        if result.probe_type == "tcp":
            port = result.observations.get("port")
            port_text = f" 端口 {port}" if port else ""
            if result.status == ProbeStatus.success:
                return f"TCP {target_val}{port_text} 可连接"
            return f"TCP {target_val}{port_text} {status_text}"

        if result.probe_type == "http":
            status_code = result.observations.get("status_code")
            resp_time = result.observations.get("response_time_ms")
            if result.status == ProbeStatus.success and status_code is not None:
                time_text = f"，响应时间 {resp_time}ms" if resp_time is not None else ""
                return f"HTTP {target_val} {status_text}，状态码 {status_code}{time_text}"
            return f"HTTP {target_val} {status_text}"

        if result.probe_type == "tls_cert":
            days = result.observations.get("days_remaining")
            if result.status == ProbeStatus.success and days is not None:
                return f"TLS 证书 {target_val} 有效，剩余 {days} 天"
            return f"TLS 证书 {target_val} {status_text}"

        return f"{result.probe_type} {target_val} {status_text}"


# ---------------------------------------------------------------------------
# OpenAIAdapter — 可选依赖
# ---------------------------------------------------------------------------


class OpenAIAdapter(AIAdapter):
    """OpenAI API 适配器。

    使用 OpenAI 兼容的 Chat Completions API。
    可选依赖：pip install openai
    """

    def __init__(self, *, api_key: str, model: str = "gpt-4o-mini", base_url: str | None = None, timeout_seconds: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, ai_input: AIInput, *, prompt: str | None = None) -> AIOutput:
        try:
            import openai
        except ImportError as exc:
            raise AIAdapterError("openai package not installed. run: pip install openai") from exc

        start = time.monotonic()

        system_prompt = self._build_system_prompt()
        user_content = self._build_user_content(ai_input, prompt)

        client_kwargs: dict[str, Any] = {
            "api_key": self._api_key,
            "timeout": self._timeout,
        }
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        client = openai.OpenAI(**client_kwargs)

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
        except Exception as exc:
            raise AIAdapterError(f"OpenAI API call failed: {exc}") from exc

        content = response.choices[0].message.content or "{}"
        duration_ms = int((time.monotonic() - start) * 1000)

        return self._parse_response(content, duration_ms)

    def _build_system_prompt(self) -> str:
        return (
            "你是一个 IT 运维助手。根据结构化运维数据生成摘要。\n"
            "严格区分事实（facts）和推断（inferences）。\n"
            "facts 只能来自输入数据，inferences 是你的推理。\n"
            "输出 JSON 格式：\n"
            '{"summary": "一句话摘要", "facts": ["事实1"], "inferences": ["推断1"], '
            '"recommendations": ["建议1"], "confidence": 0.8}\n'
            "confidence 低于 0.7 时需要人工确认。"
        )

    def _build_user_content(self, ai_input: AIInput, custom_prompt: str | None) -> str:
        data = {
            "task": ai_input.task.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in ai_input.results],
            "findings": [f.model_dump(mode="json") for f in ai_input.findings],
        }
        if custom_prompt:
            data["custom_prompt"] = custom_prompt
        return json.dumps(data, ensure_ascii=False, default=str)

    def _parse_response(self, content: str, duration_ms: int) -> AIOutput:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {"summary": content, "facts": [], "inferences": [], "recommendations": []}

        confidence = float(data.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        return AIOutput(
            summary=data.get("summary", ""),
            facts=data.get("facts", []),
            inferences=data.get("inferences", []),
            recommendations=data.get("recommendations", []),
            needs_human_review=confidence < 0.7,
            confidence=confidence,
            sources=data.get("sources", []),
            backend=self.name,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# OllamaAdapter — 可选依赖
# ---------------------------------------------------------------------------


class OllamaAdapter(AIAdapter):
    """Ollama 本地模型适配器。

    使用 Ollama REST API，适合内网环境。
    可选依赖：pip install httpx
    """

    def __init__(self, *, host: str = "http://localhost:11434", model: str = "qwen2.5:7b", timeout_seconds: int = 30) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "ollama"

    def generate(self, ai_input: AIInput, *, prompt: str | None = None) -> AIOutput:
        try:
            import httpx
        except ImportError as exc:
            raise AIAdapterError("httpx package not installed. run: pip install httpx") from exc

        start = time.monotonic()

        system_prompt = (
            "你是一个 IT 运维助手。根据结构化运维数据生成摘要。\n"
            "严格区分事实（facts）和推断（inferences）。\n"
            '输出 JSON：{"summary": "...", "facts": [], "inferences": [], '
            '"recommendations": [], "confidence": 0.8}'
        )

        user_content = json.dumps(
            {
                "task": ai_input.task.model_dump(mode="json"),
                "results": [r.model_dump(mode="json") for r in ai_input.results],
                "findings": [f.model_dump(mode="json") for f in ai_input.findings],
            },
            ensure_ascii=False,
            default=str,
        )

        try:
            resp = httpx.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "stream": False,
                    "format": "json",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise AIAdapterError(f"Ollama API call failed: {exc}") from exc

        data = resp.json()
        content = data.get("message", {}).get("content", "{}")
        duration_ms = int((time.monotonic() - start) * 1000)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"summary": content}

        confidence = float(parsed.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        return AIOutput(
            summary=parsed.get("summary", ""),
            facts=parsed.get("facts", []),
            inferences=parsed.get("inferences", []),
            recommendations=parsed.get("recommendations", []),
            needs_human_review=confidence < 0.7,
            confidence=confidence,
            sources=parsed.get("sources", []),
            backend=self.name,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# 适配器工厂
# ---------------------------------------------------------------------------


def create_adapter(config: AIConfig) -> AIAdapter:
    """根据配置创建 AI 适配器。

    TemplateAdapter 始终可用。OpenAI/Ollama 需要对应的可选依赖。
    """
    backend = config.backend

    if backend == "openai":
        if not config.openai.api_key:
            raise AIAdapterError("OpenAI backend selected but api_key is empty")
        return OpenAIAdapter(
            api_key=config.openai.api_key,
            model=config.openai.model,
            base_url=config.openai.base_url,
            timeout_seconds=config.openai.timeout_seconds,
        )

    if backend == "ollama":
        return OllamaAdapter(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )

    return TemplateAdapter()


# ---------------------------------------------------------------------------
# 领域服务
# ---------------------------------------------------------------------------


def summarize_task(
    *,
    task_id: str,
    store: SQLiteStore,
    config: OpsConfig,
    prompt: str | None = None,
) -> AIOutput:
    """对指定任务生成 AI 摘要。

    1. 从存储层加载任务和关联结果。
    2. 脱敏处理。
    3. 调用 AI 适配器。
    4. 记录审计日志。
    5. AI 调用失败时降级为 TemplateAdapter。
    """
    try:
        task = store.get_task_run(task_id)
    except TaskRecordNotFound:
        raise AIAdapterError(f"task not found: {task_id}") from None

    results = store.list_probe_results_for_task(task_id)
    findings = store.list_findings(task_id)

    ai_input = AIInput(
        task=task,
        results=results,
        findings=findings,
    )

    return _call_with_fallback(ai_input=ai_input, config=config, store=store, prompt=prompt)


def summarize_recent(
    *,
    store: SQLiteStore,
    config: OpsConfig,
    days: int = 7,
    prompt: str | None = None,
) -> AIOutput:
    """对最近 N 天的数据生成 AI 周报摘要。"""
    from datetime import timedelta

    now = datetime.now(UTC)
    start = now - timedelta(days=days)

    # 获取最近的探测结果
    all_results = store.list_probe_results_between(
        start=start.isoformat(),
        end=now.isoformat(),
        limit=500,
    )

    # 获取相关的 findings
    all_findings = store.list_findings_for_results([r.id for r in all_results])

    # 创建一个虚拟任务作为上下文
    task = TaskRun(
        id=f"ai-summary-{uuid.uuid4().hex[:8]}",
        task_type="health_check",
        source="cli",
        status=TaskStatus.success,
        started_at=start,
        ended_at=now,
        summary={"description": f"AI 周报：最近 {days} 天", "days": days},
    )

    ai_input = AIInput(
        task=task,
        results=all_results,
        findings=all_findings,
        context={"report_type": "weekly", "days": days},
    )

    return _call_with_fallback(ai_input=ai_input, config=config, store=store, prompt=prompt)


def explain_anomaly(
    *,
    task_id: str,
    store: SQLiteStore,
    config: OpsConfig,
    question: str | None = None,
) -> AIOutput:
    """解释指定任务中的异常。

    用户可以用自然语言提问，AI 基于结构化数据做解释。
    """
    try:
        task = store.get_task_run(task_id)
    except TaskRecordNotFound:
        raise AIAdapterError(f"task not found: {task_id}") from None

    results = store.list_probe_results_for_task(task_id)
    findings = store.list_findings(task_id)

    # 只关注异常结果
    anomalies = [r for r in results if r.status != ProbeStatus.success]

    ai_input = AIInput(
        task=task,
        results=anomalies,
        findings=findings,
        context={"question": question} if question else {},
    )

    return _call_with_fallback(
        ai_input=ai_input,
        config=config,
        store=store,
        prompt=question,
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _call_with_fallback(
    *,
    ai_input: AIInput,
    config: OpsConfig,
    store: SQLiteStore,
    prompt: str | None = None,
) -> AIOutput:
    """调用 AI 适配器，失败时降级为 TemplateAdapter。"""
    adapter = create_adapter(config.ai)
    template = TemplateAdapter()

    try:
        output = adapter.generate(ai_input, prompt=prompt)
        _log_ai_call(store=store, task_id=ai_input.task.id, backend=adapter.name, success=True, duration_ms=output.duration_ms or 0)
        return output
    except (AIAdapterError, Exception) as exc:
        # 降级到模板引擎
        output = template.generate(ai_input, prompt=prompt)
        _log_ai_call(
            store=store,
            task_id=ai_input.task.id,
            backend=adapter.name,
            success=False,
            duration_ms=0,
            error=str(exc),
        )
        output.inferences.append(f"[降级提示] AI 后端 {adapter.name} 调用失败，已降级为模板引擎输出。原因：{exc}")
        return output


def _log_ai_call(
    *,
    store: SQLiteStore,
    task_id: str,
    backend: str,
    success: bool,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """记录 AI 调用审计日志。"""
    log = AICallLog(
        id=f"ai-call-{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        backend=backend,
        success=success,
        duration_ms=duration_ms,
        error=error,
        called_at=datetime.now(UTC),
    )
    store.save_ai_call_log(log)

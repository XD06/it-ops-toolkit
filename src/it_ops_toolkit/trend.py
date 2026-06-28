"""趋势分析服务。

从存储层的历史数据中提取趋势洞察，供 CLI、Web 和 AI 复用。

趋势服务不负责：
- 执行探测。
- 保存数据。
- 渲染图表（由 CLI / Web 各自处理）。

它只消费结构化结果，返回结构化的趋势数据。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .storage import SQLiteStore


class TrendError(RuntimeError):
    pass


# 各探针类型支持的数值型指标
PROBE_METRICS: dict[str, list[str]] = {
    "ping": ["avg_rtt_ms", "min_rtt_ms", "max_rtt_ms", "packet_loss_percent"],
    "dns": ["duration_ms"],
    "tcp": ["duration_ms"],
    "http": ["response_time_ms"],
    "tls_cert": ["days_remaining"],
}


def get_trend(
    *,
    store: SQLiteStore,
    probe_type: str,
    target: str | None = None,
    metric: str | None = None,
    days: int = 7,
    granularity: str = "daily",
) -> dict[str, Any]:
    """获取趋势数据。

    Args:
        store: 数据存储实例。
        probe_type: 探针类型。
        target: 可选，目标筛选。
        metric: 可选，指定指标。不指定则返回所有可用指标的聚合。
        days: 查询天数范围。
        granularity: 聚合粒度，daily 或 hourly。

    Returns:
        包含趋势统计和状态分布的字典。
    """
    if probe_type not in PROBE_METRICS:
        raise TrendError(
            f"unsupported probe type: {probe_type}. "
            f"supported: {list(PROBE_METRICS.keys())}"
        )

    if granularity not in ("daily", "hourly"):
        raise TrendError(f"invalid granularity: {granularity}. use 'daily' or 'hourly'")

    if days < 1 or days > 365:
        raise TrendError(f"days must be between 1 and 365, got: {days}")

    now = datetime.now(UTC)
    start = (now - timedelta(days=days)).isoformat()
    end = now.isoformat()

    # 状态分布
    status_dist = store.get_status_distribution(
        probe_type=probe_type,
        target=target,
        start=start,
        end=end,
    )

    # 指标聚合
    metrics_to_query = [metric] if metric else PROBE_METRICS[probe_type]
    metric_stats: dict[str, list[dict[str, Any]]] = {}

    for m in metrics_to_query:
        stats = store.get_probe_stats(
            probe_type=probe_type,
            target=target,
            metric=m,
            start=start,
            end=end,
            granularity=granularity,
        )
        if stats:
            metric_stats[m] = stats

    return {
        "probe_type": probe_type,
        "target": target,
        "days": days,
        "granularity": granularity,
        "start": start,
        "end": end,
        "status_distribution": status_dist,
        "metric_stats": metric_stats,
    }


def list_available_targets(
    *,
    store: SQLiteStore,
    probe_type: str | None = None,
) -> list[dict[str, str]]:
    """列出有历史数据的目标列表。

    用于 CLI/Web 提供目标选择下拉框。
    """
    store.ensure_schema()

    conditions = []
    params: list[Any] = []

    if probe_type:
        conditions.append("probe_type = ?")
        params.append(probe_type)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with store.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT
                probe_type,
                target
            FROM probe_results
            {where_clause}
            ORDER BY probe_type ASC, target ASC
            """,
            params,
        ).fetchall()

    import json
    results: list[dict[str, str]] = []
    for row in rows:
        values = dict(row)
        # target 存储为 JSON，需要提取 value
        try:
            target_data = json.loads(values["target"])
            target_value = target_data.get("value", values["target"])
        except (json.JSONDecodeError, TypeError):
            target_value = values["target"]

        results.append(
            {
                "probe_type": values["probe_type"],
                "target": target_value,
            }
        )

    return results


def get_trend_summary(
    *,
    store: SQLiteStore,
    probe_type: str,
    target: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """获取趋势摘要（不含时间序列，只含汇总）。

    适合 AI 消费或 CLI 快速概览。
    """
    trend = get_trend(
        store=store,
        probe_type=probe_type,
        target=target,
        days=days,
        granularity="daily",
    )

    summary: dict[str, Any] = {
        "probe_type": probe_type,
        "target": target,
        "days": days,
        "total_checks": trend["status_distribution"]["total"],
        "success_rate": trend["status_distribution"]["success_rate"],
        "failed_count": trend["status_distribution"]["failed_count"],
        "timeout_count": trend["status_distribution"]["timeout_count"],
        "metrics": {},
    }

    for metric, stats in trend["metric_stats"].items():
        if not stats:
            continue
        all_avgs = [s["avg"] for s in stats if s["avg"] is not None]
        all_mins = [s["min"] for s in stats if s["min"] is not None]
        all_maxs = [s["max"] for s in stats if s["max"] is not None]
        all_p95s = [s["p95"] for s in stats if s["p95"] is not None]

        summary["metrics"][metric] = {
            "avg": round(sum(all_avgs) / len(all_avgs), 2) if all_avgs else None,
            "min": min(all_mins) if all_mins else None,
            "max": max(all_maxs) if all_maxs else None,
            "p95_avg": round(sum(all_p95s) / len(all_p95s), 2) if all_p95s else None,
            "data_points": sum(s["count"] for s in stats),
        }

    return summary

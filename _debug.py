import tempfile
from pathlib import Path

from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run, finish_task_run
from it_ops_toolkit.models import TaskStatus
from it_ops_toolkit.reports import (
    _render_health_matrix_details,
    _health_matrix_summary_payload,
    generate_report,
)

tmp = Path(tempfile.mkdtemp())
store = SQLiteStore(tmp / "ops.sqlite")
task = new_task_run(task_type="health_matrix")
task = finish_task_run(task, status=TaskStatus.success)
task = task.model_copy(
    update={
        "summary": {
            "scenario": "health_tcp_matrix",
            "title": "test",
            "source_file": "x",
            "target_count": 1,
            "success_count": 1,
            "failed_count": 0,
            "entries": [
                {
                    "row": 2,
                    "name": "a",
                    "host": "1.1.1.1",
                    "port": 80,
                    "status": "success",
                    "error": "",
                    "duration_ms": 1,
                }
            ],
        }
    }
)
store.save_task_run(task)
loaded = store.get_task_run(task.id)

payload = _health_matrix_summary_payload(loaded)
print("payload is None:", payload is None)
if payload:
    print("scenario:", payload.get("scenario"))

result = _render_health_matrix_details(loaded)
print("render lines:", len(result))
for line in result[:5]:
    print(line)

report = generate_report(
    store=store,
    source_task_id=task.id,
    output_dir=tmp / "reports",
    report_format="markdown",
)
text = Path(report.path).read_text(encoding="utf-8")
print("---REPORT HAS 批量 TCP:", "批量 TCP 端口测试" in text)

from __future__ import annotations

import json
from typing import Any

from core.utils import now_utc, write_text

METRIC_LABELS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "LLM Judge Accuracy"),
    ("mean_judge_score", "Mean Judge Score (1-5)"),
    ("samples", "Samples"),
    ("judge_exact_match_count", "Judge exact-match (no LLM call) count"),
    ("judge_fallback_count", "Judge fallback (heuristic) count"),
]


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "✅ True" if value else "❌ False"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _cell(value: Any, limit: int = 120) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _key_value_table(payload: dict[str, Any], header: tuple[str, str] = ("Field", "Value")) -> list[str]:
    lines = [f"| {header[0]} | {header[1]} |", "| :--- | :--- |"]
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            continue
        lines.append(f"| `{key}` | {_cell(_fmt(value))} |")
    return lines


def _nested_details(payload: dict[str, Any]) -> list[str]:
    nested = {key: value for key, value in payload.items() if isinstance(value, (dict, list))}
    if not nested:
        return []
    return [
        "",
        "<details><summary>Chi tiết</summary>",
        "",
        "```json",
        json.dumps(nested, indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "</details>",
    ]


def _status(passed: Any) -> str:
    if passed is None:
        return "n/a"
    return "✅ PASS" if passed else "🚨 FAIL"


def _delta(current: Any, reference: Any) -> str:
    if not isinstance(current, (int, float)) or not isinstance(reference, (int, float)):
        return "n/a"
    diff = current - reference
    if reference:
        return f"{diff:+.4f} ({diff / reference:+.1%})"
    return f"{diff:+.4f}"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase (CP3)."""
    lines = [
        "# Phase 1 Report — Baseline Pipeline",
        "",
        f"_Generated at: {now_utc().isoformat(timespec='seconds')}_",
        "",
        "## 1. Nguồn dữ liệu & Cấu hình",
        "",
        *_key_value_table(source_summary),
        "",
        "## 2. Baseline RAG Metrics",
        "",
        "| Metric | Value |",
        "| :--- | ---: |",
    ]
    for key, label in METRIC_LABELS:
        lines.append(f"| {label} | {_fmt(metrics.get(key))} |")

    by_type = metrics.get("by_question_type") or {}
    if by_type:
        lines += [
            "",
            "### Theo loại câu hỏi",
            "",
            "| Question type | Samples | Hit Rate | Token F1 | Judge Accuracy |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
        for question_type, stats in by_type.items():
            lines.append(
                f"| {question_type} | {stats['samples']} | {_fmt(stats['retrieval_hit_rate'])} | "
                f"{_fmt(stats['mean_token_f1'])} | {_fmt(stats['judge_accuracy'])} |"
            )

    ragas = metrics.get("ragas")
    if ragas:
        lines += ["", f"**Ragas:** `{_cell(ragas, limit=300)}`"]

    lines += [
        "",
        "## 3. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"**Kết quả tổng:** {_status(quality.get('success'))}",
        "",
        *_key_value_table(quality),
        *_nested_details(quality),
        "",
        "## 4. Freshness SLA",
        "",
        f"**Trạng thái:** {'✅ Fresh' if freshness.get('is_fresh') else '🚨 Stale'}",
        "",
        *_key_value_table(freshness),
        *_nested_details(freshness),
        "",
    ]
    write_text(report_path, "\n".join(lines))


def _normalize_log(corruption_log: Any) -> list[dict[str, Any]]:
    if corruption_log is None:
        return []
    if isinstance(corruption_log, list):
        return [item if isinstance(item, dict) else {"detail": item} for item in corruption_log]
    if isinstance(corruption_log, dict):
        for key in ("corruptions", "steps", "operations", "events"):
            if isinstance(corruption_log.get(key), list):
                return _normalize_log(corruption_log[key])
        return [{"corruption": key, "detail": value} for key, value in corruption_log.items()]
    return [{"detail": corruption_log}]


def _analysis(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    corrupted_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
) -> list[str]:
    """Nhan xet tu dong, chi dua tren so lieu thuc te da do duoc."""
    notes: list[str] = []
    dropped = [
        f"{label} {_fmt(baseline.get(key))} → {_fmt(corrupted.get(key))}"
        for key, label in METRIC_LABELS[:4]
        if isinstance(corrupted.get(key), (int, float))
        and isinstance(baseline.get(key), (int, float))
        and corrupted[key] < baseline[key]
    ]
    if dropped:
        notes.append("**Silent failure:** trên dữ liệu bị tiêm lỗi, pipeline vẫn chạy không báo lỗi nhưng chất lượng giảm: " + "; ".join(dropped) + ".")
    else:
        notes.append("Không quan sát thấy chỉ số nào giảm trên dữ liệu lỗi — cần xem lại kịch bản corruption hoặc test set.")

    detected = []
    if corrupted_quality.get("success") is False:
        detected.append("Quality Gate GX 1.x trả về `success=False`")
    if corrupted_freshness.get("is_fresh") is False:
        detected.append("Freshness SLA gắn cờ `is_fresh=False`")
    if detected:
        notes.append("**Observability phát hiện sự cố:** " + " và ".join(detected) + " — trong production, batch này phải bị chặn trước khi nạp vào Vector Store.")
    else:
        notes.append("**Cảnh báo:** Quality Gate và Freshness đều không phát hiện dữ liệu lỗi — cần bổ sung expectation.")

    recovered = [
        label
        for key, label in METRIC_LABELS[:4]
        if isinstance(repaired.get(key), (int, float))
        and isinstance(baseline.get(key), (int, float))
        and abs(repaired[key] - baseline[key]) < 1e-9
    ]
    if len(recovered) == 4:
        notes.append("**Repair:** toàn bộ 4 chỉ số sau phục hồi khớp tuyệt đối với baseline — dữ liệu được tái tạo từ raw snapshot đã quay về đúng trạng thái sạch.")
    else:
        notes.append(f"**Repair:** {len(recovered)}/4 chỉ số khớp baseline ({', '.join(recovered) or 'không có'}); phần chênh lệch cần được giải thích (ví dụ judge LLM không tất định).")
    return notes


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: Any = None,
    idempotency: dict[str, Any] | None = None,
    self_healing: dict[str, Any] | None = None,
) -> None:
    """Viet markdown report so sanh Baseline / Corrupted / Repaired (CP5)."""
    lines = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at: {now_utc().isoformat(timespec='seconds')}_",
        "",
        "## 1. So sánh hiệu năng RAG 3 trạng thái",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Δ Corrupted vs Baseline | Δ Repaired vs Baseline |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, label in METRIC_LABELS:
        base, corr, rep = baseline_metrics.get(key), corrupted_metrics.get(key), repaired_metrics.get(key)
        lines.append(
            f"| {label} | {_fmt(base)} | {_fmt(corr)} | {_fmt(rep)} | {_delta(corr, base)} | {_delta(rep, base)} |"
        )

    types = sorted(
        set(baseline_metrics.get("by_question_type") or {})
        | set(corrupted_metrics.get("by_question_type") or {})
        | set(repaired_metrics.get("by_question_type") or {})
    )
    if types:
        lines += [
            "",
            "### Token F1 theo loại câu hỏi",
            "",
            "| Question type | Baseline | Corrupted | Repaired |",
            "| :--- | ---: | ---: | ---: |",
        ]
        for question_type in types:
            values = [
                (metrics.get("by_question_type") or {}).get(question_type, {}).get("mean_token_f1")
                for metrics in (baseline_metrics, corrupted_metrics, repaired_metrics)
            ]
            lines.append(f"| {question_type} | " + " | ".join(_fmt(value) for value in values) + " |")

    lines += [
        "",
        "## 2. Data Observability: Quality Gate & Freshness",
        "",
        "| Check | Corrupted | Repaired |",
        "| :--- | :--- | :--- |",
        f"| GX 1.x Quality Gate (`success`) | {_status(corrupted_quality.get('success'))} | {_status(repaired_quality.get('success'))} |",
        f"| Freshness SLA (`is_fresh`) | {_status(corrupted_freshness.get('is_fresh'))} | {_status(repaired_freshness.get('is_fresh'))} |",
    ]
    for key in ("total_rows", "stale_rows", "latest_published", "oldest_published"):
        if key in corrupted_freshness or key in repaired_freshness:
            lines.append(
                f"| Freshness `{key}` | {_fmt(corrupted_freshness.get(key))} | {_fmt(repaired_freshness.get(key))} |"
            )
    lines += [
        "",
        "<details><summary>Chi tiết Quality Gate (Corrupted)</summary>",
        "",
        "```json",
        json.dumps(corrupted_quality, indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "</details>",
    ]

    entries = _normalize_log(corruption_log)
    if entries:
        columns: list[str] = []
        for entry in entries:
            for key in entry:
                if key not in columns:
                    columns.append(key)
        lines += [
            "",
            f"## 3. Nhật ký tiêm lỗi ({len(entries)} kịch bản)",
            "",
            "| # | " + " | ".join(columns) + " |",
            "| ---: | " + " | ".join(":---" for _ in columns) + " |",
        ]
        for position, entry in enumerate(entries, start=1):
            lines.append(f"| {position} | " + " | ".join(_cell(entry.get(col, "")) for col in columns) + " |")

    if idempotency:
        lines += [
            "",
            "## 4. Kiểm chứng Idempotent Repair",
            "",
            *_key_value_table(idempotency, header=("Check", "Result")),
        ]

    if self_healing:
        lines += [
            "",
            "## 5. Self-healing tự động",
            "",
            f"- **Kích hoạt:** {_fmt(self_healing.get('triggered'))} — "
            f"trạng thái `{self_healing.get('status')}`, chiến lược áp dụng `{self_healing.get('strategy_applied')}`.",
            "- **Vi phạm được tự động phát hiện:**",
            *[f"  - {reason}" for reason in self_healing.get("reasons", [])],
            "",
            "| # | Chiến lược | Rows | Quality | Fresh | Idempotent | Vấn đề còn lại | Chấp nhận |",
            "| ---: | :--- | ---: | :--- | :--- | :--- | :--- | :--- |",
        ]
        for position, attempt in enumerate(self_healing.get("attempts", []), start=1):
            lines.append(
                f"| {position} | `{attempt['strategy']}` | {attempt['rows']} | {_status(attempt['quality_success'])} | "
                f"{_status(attempt['is_fresh'])} | {_fmt(attempt['idempotent'])} | "
                f"{_cell(', '.join(attempt['remaining_issues']) or 'không')} | {_fmt(attempt['accepted'])} |"
            )
        lines += [
            "",
            "Pipeline tự chọn chiến lược theo thứ tự `rebuild_from_raw` → `rollback_last_known_good`; "
            "một bản chỉ được chấp nhận khi vượt lại Quality Gate + Freshness SLA và cho cùng hash khi chạy lại. "
            "Nếu mọi chiến lược thất bại, pipeline dừng với trạng thái `escalated` để con người xử lý.",
        ]

    lines += [
        "",
        "## 6. Phân tích",
        "",
        *[
            f"- {note}"
            for note in _analysis(
                baseline_metrics, corrupted_metrics, repaired_metrics, corrupted_quality, corrupted_freshness
            )
        ],
        "",
    ]
    write_text(report_path, "\n".join(lines))

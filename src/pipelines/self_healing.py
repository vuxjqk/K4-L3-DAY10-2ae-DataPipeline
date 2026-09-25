from __future__ import annotations

import hashlib
from typing import Any, Callable

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks

REQUIRED_COLUMNS = (
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
    "age_days",
    "text_for_embedding",
)


def content_hash(df: pd.DataFrame) -> str:
    """Hash noi dung dataframe (bo qua thu tu dong) de kiem chung idempotency."""
    columns = [col for col in ("paper_id", "title", "summary", "published", "text_for_embedding") if col in df.columns]
    canonical = df[columns].astype(str).sort_values(columns).to_csv(index=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def diagnose(df: pd.DataFrame, quality: dict[str, Any], freshness: dict[str, Any]) -> list[str]:
    """Tu dong phat hien vi pham schema / data quality / freshness. List rong = batch khoe manh."""
    reasons: list[str] = []
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        reasons.append(f"schema: missing columns {missing}")
    for check in quality.get("checks", []):
        if not check.get("success"):
            reasons.append(f"quality: {check.get('expectation')} failed")
    if not quality.get("success") and not any(reason.startswith("quality:") for reason in reasons):
        reasons.append("quality: gate success=False")
    if not freshness.get("is_fresh"):
        reasons.append(
            f"freshness: {freshness.get('stale_rows')}/{freshness.get('total_rows')} rows older than "
            f"{freshness.get('threshold_days')} days (SLA <= 25%)"
        )
    return reasons


def _observe(df: pd.DataFrame, settings: Settings, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    quality = run_data_quality_checks(df, settings, name)
    freshness = build_freshness_report(df, settings, settings.paths.quality_dir / f"{name}_freshness_report.json")
    return quality, freshness


def rebuild_from_raw(settings: Settings) -> pd.DataFrame:
    """Chien luoc 1: tai tao tu raw snapshot bat bien (nguon lineage dang tin cay nhat)."""
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), now_utc())


def rollback_last_known_good(settings: Settings) -> pd.DataFrame:
    """Chien luoc 2: rollback ve clean snapshot da vuot Quality Gate o phase 1."""
    return pd.read_json(settings.paths.clean_json, dtype={"paper_id": str, "published": str})


STRATEGIES: list[tuple[str, Callable[[Settings], pd.DataFrame]]] = [
    ("rebuild_from_raw", rebuild_from_raw),
    ("rollback_last_known_good", rollback_last_known_good),
]


def auto_heal(
    df: pd.DataFrame,
    quality: dict[str, Any],
    freshness: dict[str, Any],
    settings: Settings,
    report_name: str = "repaired",
) -> dict[str, Any]:
    """Self-healing: chan doan batch, neu vi pham thi tu dong thu tung chien luoc repair
    cho den khi du lieu vuot lai Quality Gate + Freshness SLA. Khong can can thiep tay.

    Tra ve dict gom `dataframe`, `quality`, `freshness` cua ban duoc chap nhan va `log` de audit.
    """
    reasons = diagnose(df, quality, freshness)
    log: dict[str, Any] = {
        "checked_at": now_utc().isoformat(timespec="seconds"),
        "triggered": bool(reasons),
        "reasons": reasons,
        "attempts": [],
        "status": "healthy_no_action",
        "strategy_applied": None,
    }
    if not reasons:
        write_json(settings.paths.self_healing_log, log)
        return {"dataframe": df, "quality": quality, "freshness": freshness, "log": log}

    for name, strategy in STRATEGIES:
        candidate = strategy(settings)
        candidate_quality, candidate_freshness = _observe(candidate, settings, report_name)
        remaining = diagnose(candidate, candidate_quality, candidate_freshness)
        # Chay lai cung chien luoc lan 2: ket qua phai trung hash -> repair idempotent.
        idempotent = content_hash(strategy(settings)) == content_hash(candidate)
        accepted = not remaining and idempotent
        log["attempts"].append(
            {
                "strategy": name,
                "rows": len(candidate),
                "quality_success": candidate_quality.get("success"),
                "is_fresh": candidate_freshness.get("is_fresh"),
                "idempotent": idempotent,
                "remaining_issues": remaining,
                "accepted": accepted,
            }
        )
        if accepted:
            log["status"] = "healed"
            log["strategy_applied"] = name
            write_json(settings.paths.self_healing_log, log)
            return {"dataframe": candidate, "quality": candidate_quality, "freshness": candidate_freshness, "log": log}

    log["status"] = "escalated"
    write_json(settings.paths.self_healing_log, log)
    raise RuntimeError(
        f"Self-healing exhausted all strategies; manual intervention required. See {settings.paths.self_healing_log}."
    )

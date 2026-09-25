from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import jsonable, load_or_build_test_set, read_clean_json, save_clean_artifacts
from retrieval.index import LocalEmbeddingIndex

COMPARED_METRICS = [
    ("retrieval_hit_rate", "Hit Rate"),
    ("mean_token_f1", "Token F1"),
    ("judge_accuracy", "Judge Acc"),
    ("mean_judge_score", "Judge Score"),
]


def _content_hash(df: pd.DataFrame) -> str:
    """Hash noi dung dataframe (bo qua thu tu dong) de kiem chung idempotency."""
    columns = [col for col in ("paper_id", "title", "summary", "published", "text_for_embedding") if col in df.columns]
    canonical = df[columns].astype(str).sort_values(columns).to_csv(index=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _observe(df: pd.DataFrame, settings: Settings, name: str, quality_path: Path) -> tuple[dict, dict]:
    quality = jsonable(run_data_quality_checks(df, settings, name))
    write_json(quality_path, quality)
    freshness = jsonable(
        build_freshness_report(df, settings, settings.paths.quality_dir / f"{name}_freshness_report.json")
    )
    return quality, freshness


def _evaluate(df: pd.DataFrame, settings: Settings, embeddings_path: Path, metrics_path: Path, answers_path: Path):
    index = LocalEmbeddingIndex.build(df, settings, embeddings_path)
    bundle = evaluate_pipeline(settings, index, settings.paths.eval_testset, metrics_path, answers_path)
    return index, bundle.summary


def repair_from_raw(settings: Settings) -> pd.DataFrame:
    """Idempotent repair: luon tai tao tu raw snapshot, khong vá tay tren dataframe bi hong."""
    records = load_raw_records(settings.paths.raw_records_json)
    return build_clean_dataframe(records, now_utc())


def _print_comparison(baseline: dict, corrupted: dict, repaired: dict) -> None:
    print()
    print(f"{'Metric':<14}{'Baseline':>12}{'Corrupted':>12}{'Repaired':>12}")
    print("-" * 50)
    for key, label in COMPARED_METRICS:
        print(f"{label:<14}{baseline.get(key, 0):>12.4f}{corrupted.get(key, 0):>12.4f}{repaired.get(key, 0):>12.4f}")
    print()


def main() -> None:
    settings = load_settings()
    paths = settings.paths

    print("[1/6] Load baseline metrics & clean dataset")
    if not paths.baseline_metrics.exists() or not paths.clean_json.exists():
        raise FileNotFoundError("Baseline artifacts not found — run `python script/run_phase1.py` first.")
    baseline_metrics = read_json(paths.baseline_metrics)
    clean_df = read_clean_json(paths.clean_json)
    load_or_build_test_set(clean_df, settings)
    print(f"      -> {len(clean_df)} clean rows, baseline hit_rate={baseline_metrics['retrieval_hit_rate']:.4f}")

    print("[2/6] Corruption: tiêm lỗi dữ liệu")
    corrupted_df = corrupt_clean_dataframe(clean_df.copy(), paths.corruption_log)
    save_clean_artifacts(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    corruption_log = read_json(paths.corruption_log) if paths.corruption_log.exists() else None
    print(f"      -> {len(corrupted_df)} corrupted rows, log -> {paths.corruption_log.relative_to(paths.project_dir)}")

    print("[3/6] Observability trên dữ liệu lỗi")
    corrupted_quality, corrupted_freshness = _observe(
        corrupted_df, settings, "corrupted", paths.corrupted_quality_report
    )
    print(
        f"      -> quality success={corrupted_quality.get('success')} | is_fresh={corrupted_freshness.get('is_fresh')}"
    )
    if not corrupted_quality.get("success") or not corrupted_freshness.get("is_fresh"):
        print("      🚨 ALERT: dữ liệu lỗi bị phát hiện — production sẽ chặn batch này. "
              "Lab vẫn index để đo mức suy giảm (silent failure).")

    print(f"[4/6] Evaluate trên collection '{settings.corrupted_collection_name}'")
    _, corrupted_metrics = _evaluate(
        corrupted_df, settings, paths.corrupted_embeddings_json, paths.corrupted_metrics, paths.corrupted_answers
    )

    print("[5/6] Idempotent repair từ raw snapshot")
    repaired_df = repair_from_raw(settings)
    second_pass_df = repair_from_raw(settings)
    save_clean_artifacts(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    repaired_quality, repaired_freshness = _observe(
        repaired_df, settings, "repaired", paths.quality_dir / "repaired_quality_report.json"
    )
    idempotency = {
        "repaired_rows": len(repaired_df),
        "baseline_rows": len(clean_df),
        "repair_run_twice_identical": _content_hash(repaired_df) == _content_hash(second_pass_df),
        "repaired_matches_baseline": _content_hash(read_clean_json(paths.repaired_clean_json))
        == _content_hash(clean_df),
        "repaired_quality_success": repaired_quality.get("success"),
    }
    print(f"      -> {idempotency}")
    if not repaired_quality.get("success"):
        raise RuntimeError("Quality Gate still failing after repair — refusing to index repaired data.")
    _, repaired_metrics = _evaluate(
        repaired_df, settings, paths.repaired_embeddings_json, paths.repaired_metrics, paths.repaired_answers
    )

    print("[6/6] Báo cáo đối chiếu 3 trạng thái")
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        corruption_log=corruption_log,
        idempotency=idempotency,
    )
    _print_comparison(baseline_metrics, corrupted_metrics, repaired_metrics)
    print(f"Report -> {paths.comparison_report.relative_to(paths.project_dir)}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import jsonable, load_or_build_test_set, read_clean_json, save_clean_artifacts
from pipelines.self_healing import auto_heal, content_hash
from retrieval.index import LocalEmbeddingIndex

COMPARED_METRICS = [
    ("retrieval_hit_rate", "Hit Rate"),
    ("mean_token_f1", "Token F1"),
    ("judge_accuracy", "Judge Acc"),
    ("mean_judge_score", "Judge Score"),
]


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

    print("[5/6] Self-healing: tự chẩn đoán & tự động repair (không can thiệp tay)")
    healing = auto_heal(corrupted_df, corrupted_quality, corrupted_freshness, settings)
    healing_log = healing["log"]
    print(f"      -> triggered={healing_log['triggered']} | reasons={len(healing_log['reasons'])}")
    for reason in healing_log["reasons"]:
        print(f"         - {reason}")
    for attempt in healing_log["attempts"]:
        print(
            f"      -> {attempt['strategy']}: quality={attempt['quality_success']} fresh={attempt['is_fresh']} "
            f"idempotent={attempt['idempotent']} accepted={attempt['accepted']}"
        )
    print(f"      -> status={healing_log['status']} | strategy={healing_log['strategy_applied']}")
    repaired_df = healing["dataframe"]
    save_clean_artifacts(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    repaired_quality, repaired_freshness = jsonable(healing["quality"]), jsonable(healing["freshness"])
    write_json(paths.quality_dir / "repaired_quality_report.json", repaired_quality)
    accepted = next((a for a in healing_log["attempts"] if a["accepted"]), None)
    idempotency = {
        "repaired_rows": len(repaired_df),
        "baseline_rows": len(clean_df),
        "repair_run_twice_identical": accepted["idempotent"] if accepted else None,
        "repaired_matches_baseline": content_hash(read_clean_json(paths.repaired_clean_json))
        == content_hash(clean_df),
        "repaired_quality_success": repaired_quality.get("success"),
    }
    print(f"      -> {idempotency}")
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
        self_healing=healing_log,
    )
    _print_comparison(baseline_metrics, corrupted_metrics, repaired_metrics)
    print(f"Report -> {paths.comparison_report.relative_to(paths.project_dir)}")


if __name__ == "__main__":
    main()

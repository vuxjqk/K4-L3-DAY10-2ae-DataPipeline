from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings, normalized_provider
from core.utils import ensure_parent, now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

DEMO_QUESTIONS = [
    "Which papers discuss data quality gates or data observability for RAG systems?",
    "What does the corpus say about freshness SLAs for LLM knowledge augmentation?",
]


def load_or_fetch_records(settings: Settings) -> list[PaperRecord]:
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        return load_raw_records(settings.paths.raw_records_json)
    return fetch_source_records(settings)


def save_clean_artifacts(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", indent=2, date_format="iso", force_ascii=False)


def read_clean_json(json_path: Path) -> pd.DataFrame:
    return pd.read_json(json_path, dtype={"paper_id": str, "published": str})


def jsonable(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=str))


def load_or_build_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        return read_json(settings.paths.eval_testset)
    return build_test_set(df, settings.paths.eval_testset)


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex) -> list[dict[str, Any]]:
    try:
        agent = build_agent(settings, index)
    except Exception as exc:
        return [{"skipped": f"Agent unavailable ({normalized_provider(settings)}): {exc}"}]
    answers = []
    for question in DEMO_QUESTIONS:
        try:
            answers.append({"question": question, "answer": run_agent_question(agent, question)})
        except Exception as exc:
            answers.append({"question": question, "error": f"{type(exc).__name__}: {exc}"})
    return answers


def main() -> None:
    settings = load_settings()
    paths = settings.paths

    print("[1/7] Ingestion: load raw snapshot hoặc fetch Crossref API")
    records = load_or_fetch_records(settings)
    print(f"      -> {len(records)} raw records")

    print("[2/7] Cleaning")
    run_date = now_utc()
    df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(df, paths.clean_csv, paths.clean_json)
    print(f"      -> {len(df)} clean rows -> {paths.clean_csv.relative_to(paths.project_dir)}")

    print("[3/7] Quality Gate (GX 1.x) + Freshness SLA")
    quality = jsonable(run_data_quality_checks(df, settings, "baseline"))
    write_json(paths.baseline_quality_report, quality)
    freshness = jsonable(build_freshness_report(df, settings, paths.freshness_report))
    print(f"      -> quality success={quality.get('success')} | is_fresh={freshness.get('is_fresh')}")
    if not quality.get("success"):
        raise RuntimeError(
            f"Quality Gate failed on baseline data — refusing to index. See {paths.baseline_quality_report}."
        )

    print(f"[4/7] Index ChromaDB collection '{settings.baseline_collection_name}'")
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)
    print(f"      -> {index.collection.count()} vectors")

    print("[5/7] Test set")
    test_set = load_or_build_test_set(df, settings)
    print(f"      -> {len(test_set)} questions -> {paths.eval_testset.relative_to(paths.project_dir)}")

    print("[6/7] Baseline evaluation")
    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)
    metrics = bundle.summary
    print(
        f"      -> hit_rate={metrics['retrieval_hit_rate']:.4f} | token_f1={metrics['mean_token_f1']:.4f} "
        f"| judge_acc={metrics['judge_accuracy']:.4f}"
    )

    print("[7/7] Phase 1 report + agent demo")
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "raw_records": len(records),
        "clean_rows": len(df),
        "run_date": run_date.isoformat(timespec="seconds"),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "indexed_vectors": index.collection.count(),
        "top_k": settings.top_k,
        "llm_provider": normalized_provider(settings),
        "llm_model": settings.model_name,
        "test_set_size": len(test_set),
    }
    generate_phase1_report(paths.baseline_report, source_summary, metrics, quality, freshness)
    write_json(paths.demo_answers, _run_agent_demo(settings, index))
    print(f"      -> {paths.baseline_report.relative_to(paths.project_dir)}")
    print("Phase 1 hoàn thành.")


if __name__ == "__main__":
    main()

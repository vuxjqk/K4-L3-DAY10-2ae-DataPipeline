from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
import os
import sys
import time
import types
from typing import Any

from datasets import Dataset
from pydantic import BaseModel, Field

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json
from retrieval.embeddings import MiniLMEmbeddings
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import answer_question


JUDGE_MAX_ATTEMPTS = 3
JUDGE_BACKOFF_SECONDS = 20
FALLBACK_JUDGE_REASONING = "Fallback heuristic judge used because the LLM evaluator was unavailable."
EXACT_MATCH_JUDGE_REASONING = "Exact match with the reference answer; LLM judge call skipped."
_judge_state = {"daily_quota_exhausted": False}


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    correct: bool
    reasoning: str


@dataclass(frozen=True)
class EvaluationBundle:
    summary: dict[str, Any]
    answers: list[dict[str, Any]]


def _token_f1(reference: str, prediction: str) -> float:
    ref_tokens = normalize_whitespace(reference).lower().split()
    pred_tokens = normalize_whitespace(prediction).lower().split()
    if not ref_tokens or not pred_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    pred_set = set(pred_tokens)
    overlap = len(ref_set & pred_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_set)
    recall = overlap / len(ref_set)
    return 2 * precision * recall / (precision + recall)


def _judge_answer(settings: Settings, question: str, reference: str, prediction: str) -> JudgeVerdict:
    prompt = f"""
Evaluate the model answer against the reference answer.

Question: {question}
Reference answer: {reference}
Model answer: {prediction}

Return:
- score from 1 to 5
- correct = true only when the answer is materially correct
- short reasoning
""".strip()
    if normalize_whitespace(reference).lower() == normalize_whitespace(prediction).lower():
        # Trung khop tuyet doi -> chac chan dung, khong ton quota LLM (free tier chi ~20 request/ngay).
        return JudgeVerdict(score=5, correct=True, reasoning=EXACT_MATCH_JUDGE_REASONING)
    try:
        if _judge_state["daily_quota_exhausted"]:
            raise RuntimeError("LLM judge disabled: daily quota exhausted earlier in this run.")
        llm = build_llm(settings=settings, temperature=0.0).with_structured_output(JudgeVerdict)
        for attempt in range(JUDGE_MAX_ATTEMPTS):
            try:
                return llm.invoke(prompt)
            except Exception as exc:
                # Het quota theo ngay -> retry vo ich, ngat han LLM judge cho phan con lai cua run.
                if "PerDay" in str(exc):
                    _judge_state["daily_quota_exhausted"] = True
                    raise
                # Loi tam thoi (429 theo phut, ngat ket noi) -> backoff roi thu lai truoc khi fallback.
                if attempt == JUDGE_MAX_ATTEMPTS - 1:
                    raise
                time.sleep(JUDGE_BACKOFF_SECONDS * (attempt + 1))
    except Exception:
        score = 5 if _token_f1(reference, prediction) >= 0.95 else 3 if _token_f1(reference, prediction) >= 0.5 else 1
        return JudgeVerdict(
            score=score,
            correct=score >= 3,
            reasoning=FALLBACK_JUDGE_REASONING,
        )


def _run_ragas(settings: Settings, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if os.getenv("RUN_RAGAS", "").lower() not in {"1", "true", "yes"}:
        return {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}
    try:
        if "langchain_community.chat_models.vertexai" not in sys.modules:
            shim = types.ModuleType("langchain_community.chat_models.vertexai")
            shim.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules["langchain_community.chat_models.vertexai"] = shim
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        dataset = Dataset.from_dict(
            {
                "question": [item["question"] for item in answers],
                "answer": [item["answer"] for item in answers],
                "ground_truth": [item["ground_truth"] for item in answers],
                "contexts": [item["retrieved_contexts"] for item in answers],
            }
        )
        result = evaluate(
            dataset,
            metrics=[answer_relevancy, context_precision, context_recall, faithfulness],
            llm=build_llm(settings=settings, temperature=0.0),
            embeddings=MiniLMEmbeddings(settings.embedding_model),
        )
        return dict(result)
    except Exception as exc:  # pragma: no cover
        return {"error": f"Ragas evaluation failed: {exc}"}


def _breakdown_by_question_type(answers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in answers:
        grouped.setdefault(item["question_type"], []).append(item)
    return {
        question_type: {
            "samples": len(items),
            "retrieval_hit_rate": mean(1.0 if item["retrieval_hit"] else 0.0 for item in items),
            "mean_token_f1": mean(item["token_f1"] for item in items),
            "judge_accuracy": mean(1.0 if item["judge"]["correct"] else 0.0 for item in items),
        }
        for question_type, items in sorted(grouped.items())
    }


def evaluate_pipeline(
    settings: Settings,
    index: LocalEmbeddingIndex,
    test_set_path,
    metrics_output_path,
    answers_output_path,
) -> EvaluationBundle:
    test_set = read_json(test_set_path)
    answers: list[dict[str, Any]] = []

    for item in test_set:
        result = answer_question(item["question"], settings=settings, index=index)
        judge = _judge_answer(settings, item["question"], item["ground_truth"], result.answer)
        retrieval_hit = any(doc_id in item["ground_truth_doc_ids"] for doc_id in result.retrieved_doc_ids)
        answers.append(
            {
                "id": item["id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "ground_truth_doc_ids": item["ground_truth_doc_ids"],
                "answer": result.answer,
                "retrieved_doc_ids": result.retrieved_doc_ids,
                "retrieved_contexts": result.retrieved_contexts,
                "retrieval_hit": retrieval_hit,
                "token_f1": _token_f1(item["ground_truth"], result.answer),
                "judge": judge.model_dump(),
            }
        )

    summary = {
        "samples": len(answers),
        "retrieval_hit_rate": mean(1.0 if item["retrieval_hit"] else 0.0 for item in answers),
        "mean_token_f1": mean(item["token_f1"] for item in answers),
        "judge_accuracy": mean(1.0 if item["judge"]["correct"] else 0.0 for item in answers),
        "mean_judge_score": mean(item["judge"]["score"] for item in answers),
        "judge_exact_match_count": sum(item["judge"]["reasoning"] == EXACT_MATCH_JUDGE_REASONING for item in answers),
        "judge_fallback_count": sum(item["judge"]["reasoning"] == FALLBACK_JUDGE_REASONING for item in answers),
        "by_question_type": _breakdown_by_question_type(answers),
    }
    summary["ragas"] = _run_ragas(settings, answers)

    bundle = EvaluationBundle(summary=summary, answers=answers)
    write_json(metrics_output_path, summary)
    write_json(answers_output_path, answers)
    return bundle

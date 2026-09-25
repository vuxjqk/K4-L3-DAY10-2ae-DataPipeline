from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json

TEST_SET_SIZE = 10
QUESTION_TYPES = ("summary", "authors", "date", "categories")

# Cau hoi phai khop voi cac nhanh trong retrieval.qa._extract_answer.
QUESTION_TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _as_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return normalize_whitespace(str(value))


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(_as_text(row["summary"]))
    if question_type == "authors":
        return _as_text(row["authors_joined"])
    if question_type == "date":
        return _as_text(row["published"])[:10]
    return _as_text(row["categories_joined"])


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set gom 10 cau hoi phu 4 nhom summary/authors/date/categories.

    - Chon 10 paper khac nhau, rai deu tren truc thoi gian (moi nhat -> cu nhat) de
      test set nhay cam voi ca loi "drop latest records" lan "stale date".
    - Loai cau hoi xoay vong theo QUESTION_TYPES -> 3 summary, 3 authors, 2 date, 2 categories.
    - Deterministic: cung dataframe dau vao luon sinh cung test set.
    """
    required = {"paper_id", "title", "summary", "authors_joined", "categories_joined", "published"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Clean dataframe is missing columns for test set: {sorted(missing)}")

    candidates = df.dropna(subset=["paper_id", "title"]).drop_duplicates(subset=["paper_id"])
    candidates = candidates[candidates["title"].map(_as_text).str.len() > 0]
    # Title chua dau nhay don se lam hong regex lookup trong qa.answer_question.
    candidates = candidates[~candidates["title"].astype(str).str.contains("'")]
    if len(candidates) < TEST_SET_SIZE:
        raise ValueError(
            f"Need at least {TEST_SET_SIZE} distinct documents to build the test set, got {len(candidates)}."
        )

    candidates = candidates.assign(_published_key=candidates["published"].map(_as_text))
    candidates = candidates.sort_values(["_published_key", "paper_id"], ascending=[False, True])
    candidates = candidates.reset_index(drop=True)

    step = len(candidates) / TEST_SET_SIZE
    picked = candidates.iloc[[int(i * step) for i in range(TEST_SET_SIZE)]]

    test_set: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(picked.iterrows()):
        question_type = QUESTION_TYPES[position % len(QUESTION_TYPES)]
        title = _as_text(row["title"])
        test_set.append(
            {
                "id": f"eval_{position + 1:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=title),
                "ground_truth": _ground_truth(row, question_type),
                "ground_truth_doc_ids": [_as_text(row["paper_id"])],
            }
        )

    write_json(output_path, test_set)
    return test_set

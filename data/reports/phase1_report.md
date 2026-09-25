# Phase 1 Report — Baseline Pipeline

_Generated at: 2026-09-25T09:04:15+00:00_

## 1. Nguồn dữ liệu & Cấu hình

| Field | Value |
| :--- | :--- |
| `source_api` | Crossref REST API |
| `source_query` | agentic retrieval augmented generation large language model |
| `source_filter` | from-pub-date:2026-03-29,has-abstract:true |
| `raw_records` | 24 |
| `clean_rows` | 24 |
| `run_date` | 2026-09-25T09:04:06+00:00 |
| `embedding_model` | sentence-transformers/all-MiniLM-L6-v2 |
| `collection_name` | papers-baseline |
| `indexed_vectors` | 24 |
| `top_k` | 4 |
| `llm_provider` | gemini |
| `llm_model` | gemini-3.7-flash |
| `test_set_size` | 10 |

## 2. Baseline RAG Metrics

| Metric | Value |
| :--- | ---: |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 1.0000 |
| LLM Judge Accuracy | 1.0000 |
| Mean Judge Score (1-5) | 5 |
| Samples | 10 |
| Judge exact-match (no LLM call) count | 10 |
| Judge fallback (heuristic) count | 0 |

### Theo loại câu hỏi

| Question type | Samples | Hit Rate | Token F1 | Judge Accuracy |
| :--- | ---: | ---: | ---: | ---: |
| authors | 3 | 1.0000 | 1.0000 | 1.0000 |
| categories | 2 | 1.0000 | 1.0000 | 1.0000 |
| date | 2 | 1.0000 | 1.0000 | 1.0000 |
| summary | 3 | 1.0000 | 1.0000 | 1.0000 |

**Ragas:** `{"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}`

## 3. Data Quality Gate (Great Expectations 1.x)

**Kết quả tổng:** ✅ PASS

| Field | Value |
| :--- | :--- |
| `report_name` | baseline |
| `success` | ✅ True |
| `row_count` | 24 |

<details><summary>Chi tiết</summary>

```json
{
  "checks": [
    {
      "expectation": "ExpectTableRowCountToBeBetween",
      "success": true
    },
    {
      "expectation": "ExpectColumnValuesToNotBeNull",
      "success": true
    },
    {
      "expectation": "ExpectColumnValuesToNotBeNull",
      "success": true
    },
    {
      "expectation": "ExpectColumnValuesToNotBeNull",
      "success": true
    },
    {
      "expectation": "ExpectColumnValuesToBeUnique",
      "success": true
    },
    {
      "expectation": "ExpectColumnValueLengthsToBeBetween",
      "success": true
    }
  ]
}
```

</details>

## 4. Freshness SLA

**Trạng thái:** ✅ Fresh

| Field | Value |
| :--- | :--- |
| `latest_published` | 2026-07-22 |
| `oldest_published` | 2026-03-28 |
| `stale_rows` | 1 |
| `total_rows` | 24 |
| `stale_ratio` | 0.0417 |
| `threshold_days` | 180 |
| `is_fresh` | ✅ True |

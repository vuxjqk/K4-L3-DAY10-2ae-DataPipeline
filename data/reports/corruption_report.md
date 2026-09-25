# Corruption Report — Baseline vs Corrupted vs Repaired

_Generated at: 2026-09-25T09:07:56+00:00_

## 1. So sánh hiệu năng RAG 3 trạng thái

| Metric | Baseline | Corrupted | Repaired | Δ Corrupted vs Baseline | Δ Repaired vs Baseline |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Retrieval Hit Rate | 1.0000 | 0.7000 | 1.0000 | -0.3000 (-30.0%) | +0.0000 (+0.0%) |
| Mean Token F1 | 1.0000 | 0.7720 | 1.0000 | -0.2280 (-22.8%) | +0.0000 (+0.0%) |
| LLM Judge Accuracy | 1.0000 | 0.8000 | 1.0000 | -0.2000 (-20.0%) | +0.0000 (+0.0%) |
| Mean Judge Score (1-5) | 5 | 4 | 5 | -1.0000 (-20.0%) | +0.0000 (+0.0%) |
| Samples | 10 | 10 | 10 | +0.0000 (+0.0%) | +0.0000 (+0.0%) |
| Judge exact-match (no LLM call) count | 10 | 7 | 10 | -3.0000 (-30.0%) | +0.0000 (+0.0%) |
| Judge fallback (heuristic) count | 0 | 2 | 0 | +2.0000 | +0.0000 |

### Token F1 theo loại câu hỏi

| Question type | Baseline | Corrupted | Repaired |
| :--- | ---: | ---: | ---: |
| authors | 1.0000 | 1.0000 | 1.0000 |
| categories | 1.0000 | 1.0000 | 1.0000 |
| date | 1.0000 | 0.5000 | 1.0000 |
| summary | 1.0000 | 0.5733 | 1.0000 |

## 2. Data Observability: Quality Gate & Freshness

| Check | Corrupted | Repaired |
| :--- | :--- | :--- |
| GX 1.x Quality Gate (`success`) | 🚨 FAIL | ✅ PASS |
| Freshness SLA (`is_fresh`) | 🚨 FAIL | ✅ PASS |
| Freshness `total_rows` | 21 | 24 |
| Freshness `stale_rows` | 7 | 1 |
| Freshness `latest_published` | 2026-06-12 | 2026-07-22 |
| Freshness `oldest_published` | 2025-03-28 | 2026-03-28 |

<details><summary>Chi tiết Quality Gate (Corrupted)</summary>

```json
{
  "report_name": "corrupted",
  "success": false,
  "row_count": 21,
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
      "success": false
    },
    {
      "expectation": "ExpectColumnValueLengthsToBeBetween",
      "success": false
    }
  ]
}
```

</details>

## 3. Nhật ký tiêm lỗi (6 kịch bản)

| # | corruption | detail |
| ---: | :--- | :--- |
| 1 | drop_latest_records | {"count": 5, "paper_ids": ["10.1145/3637528.3671812", "10.1145/3637528.3671808", "10.1145/3637528.3671804", "10.1145/... |
| 2 | blank_summary | {"count": 2, "paper_ids": ["10.1145/3637528.3671824", "10.1145/3637528.3671823"]} |
| 3 | inject_noise | {"count": 2, "paper_ids": ["10.1145/3637528.3671822", "10.1145/3637528.3671821"]} |
| 4 | truncate_title | {"count": 2, "paper_ids": ["10.1145/3637528.3671810", "10.1145/3637528.3671820"]} |
| 5 | stale_date | {"count": 7, "paper_ids": ["10.1145/3637528.3671813", "10.1145/3637528.3671801", "10.1145/3637528.3671811", "10.1145/... |
| 6 | duplicate_rows | {"count": 2, "paper_ids": ["10.1145/3637528.3671824", "10.1145/3637528.3671823"]} |

## 4. Kiểm chứng Idempotent Repair

| Check | Result |
| :--- | :--- |
| `repaired_rows` | 24 |
| `baseline_rows` | 24 |
| `repair_run_twice_identical` | ✅ True |
| `repaired_matches_baseline` | ✅ True |
| `repaired_quality_success` | ✅ True |

## 5. Phân tích

- **Silent failure:** trên dữ liệu bị tiêm lỗi, pipeline vẫn chạy không báo lỗi nhưng chất lượng giảm: Retrieval Hit Rate 1.0000 → 0.7000; Mean Token F1 1.0000 → 0.7720; LLM Judge Accuracy 1.0000 → 0.8000; Mean Judge Score (1-5) 5 → 4.
- **Observability phát hiện sự cố:** Quality Gate GX 1.x trả về `success=False` và Freshness SLA gắn cờ `is_fresh=False` — trong production, batch này phải bị chặn trước khi nạp vào Vector Store.
- **Repair:** toàn bộ 4 chỉ số sau phục hồi khớp tuyệt đối với baseline — dữ liệu được tái tạo từ raw snapshot đã quay về đúng trạng thái sạch.

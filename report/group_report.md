# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4                          |
| Tên nhóm         | 2ae                         |
| Repository         | https://github.com/vuxjqk/K4-L3-DAY10-2ae-DataPipeline |
| Ngày hoàn thành | 2026-09-25                  |

### Thành viên và phân công

Nhóm có 2 thành viên (ít hơn mức 3–5 của template), nên mỗi người sở hữu nhiều khối hơn so với bảng phân công gợi ý.

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Trần Anh Vũ | 2A202602570 | Evaluation, Reporting & Integration owner | `src/evaluation/testset.py`, `src/evaluation/metrics.py` (mở rộng), `src/observability/reporting.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`; chạy tích hợp và sinh toàn bộ artifacts |
| 2 | Nguyễn Bá Chính | 2A202602654 | Data Foundation, Quality & Corruption owner | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, `src/observability/quality.py`, `src/ingestion/corruption.py` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm đã hoàn thành đủ CP0–CP5: thu thập 24 bài báo từ snapshot Crossref, làm sạch thành 24 dòng, kiểm định bằng Great Expectations 1.x và Freshness SLA, index vào ChromaDB (`all-MiniLM-L6-v2`), sinh bộ test 10 câu thuộc 4 loại câu hỏi, rồi chạy cả hai flow `run_phase1.py` và `run_corruption_flow.py` end-to-end (exit code 0).

Baseline sinh đủ các artifact: `papers_clean.csv/json`, `test_set.json`, `baseline_metrics.json`, các quality report và `phase1_report.md`. Trên baseline, cả Hit Rate và Token F1 đều đạt 1.0.

Sau khi tiêm 6 loại lỗi, Quality Gate chuyển sang **FAIL** (vi phạm unique `paper_id` và độ dài `summary`) và Freshness chuyển sang **stale** (33,3% dòng quá 180 ngày, vượt ngưỡng 25%). Agent vẫn trả lời bình thường mà không báo lỗi, nhưng Hit Rate giảm từ 1.0 xuống 0.7 và Token F1 từ 1.0 xuống 0.772. Lỗi gây hại rõ nhất là **drop latest records**: 3/10 câu mất tài liệu đích, trong đó có câu hỏi về ngày xuất bản bị trả lời sai một cách tự tin.

Repair tái tạo lại dữ liệu từ `data/raw/crossref_records.json`. Kết quả phục hồi 100% cả 4 chỉ số. Chạy repair hai lần cho kết quả giống hệt nhau và trùng hash với baseline.

Giới hạn lớn nhất là quota free tier của Gemini (khoảng 20 request/ngày/model). Vì vậy LLM judge chỉ được gọi cho những câu không khớp tuyệt đối: 2/30 câu phải dùng heuristic dự phòng, và agent demo không chạy được do lỗi 503/429.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (fallback: data/raw/crossref_response.json)
    -> data/raw/crossref_records.json                      (parse + chuẩn hóa)
    -> data/clean/papers_clean.csv|json                    (cleaning, age_days, text_for_embedding)
    -> Quality Gate GX 1.x + Freshness SLA                 (chặn index nếu baseline FAIL)
    -> MiniLM embedding + ChromaDB `papers-baseline`
    -> data/eval/test_set.json -> baseline_metrics.json -> phase1_report.md
    -> corruption (6 kịch bản) -> corruption_log.json
    -> quality/freshness trên dữ liệu lỗi (ALERT) -> `papers-corrupted` -> corrupted_metrics.json
    -> repair: rebuild từ raw records (chạy 2 lần, so hash) -> `papers-repaired` -> repaired_metrics.json
    -> corruption_report.md (Baseline vs Corrupted vs Repaired)
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref REST API / snapshot `crossref_response.json` | Gọi API, retry 3 lần với 429/503 và backoff `2^attempt`, fallback snapshot, bỏ thẻ JATS/HTML, parse DOI/title/abstract/author/subject/date | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Nguyễn Bá Chính |
| Cleaning          | `list[PaperRecord]`, `run_date` | Chuẩn hóa khoảng trắng, bỏ record thiếu `paper_id`/title/published, tính `age_days`, sinh `text_for_embedding`, dedup theo `paper_id`, sort | `data/clean/papers_clean.csv`, `papers_clean.json` | Nguyễn Bá Chính (logic), Trần Anh Vũ (ghi artifact trong pipeline) |
| Embedding/index   | Clean dataframe | `all-MiniLM-L6-v2` (normalize), ChromaDB cosine, 3 collection tách biệt | `data/chroma/`, `data/embeddings/*.json` | Starter code; Trần Anh Vũ tích hợp |
| Evaluation        | Clean dataframe, index | Sinh 10 câu hỏi deterministic; Hit Rate, Token F1, LLM judge, breakdown theo loại câu hỏi | `data/eval/test_set.json`, `data/results/*_metrics.json`, `*_answers.json` | Trần Anh Vũ |
| Observability     | Dataframe (baseline/corrupted/repaired) | 6 expectation GX 1.x (ephemeral context), Freshness SLA `age_days > 180` với ngưỡng tỷ lệ 25% | `data/quality/*.json` | Nguyễn Bá Chính (checks), Trần Anh Vũ (reporting) |
| Corruption/repair | Clean dataframe / raw records | 6 kịch bản lỗi + log; repair từ raw, kiểm idempotency bằng hash | `corruption_log.json`, `papers_clean_corrupted/repaired.*` | Nguyễn Bá Chính (corruption), Trần Anh Vũ (repair flow) |
| Orchestration     | Settings, toàn bộ module | Thứ tự chạy phase 1 và corruption flow, gate, in bảng 3 trạng thái | `phase1_report.md`, `corruption_report.md` | Trần Anh Vũ |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `gemini`            |
| `LLM_MODEL`                | `gemini-3.7-flash` (`gemini-2.5-flash` của starter trả 404 với tài khoản mới) |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results=24`) |
| Retrieval`top_k`           | 4                   |
| Freshness threshold          | 180 ngày; `is_fresh=False` khi tỷ lệ stale > 25% |
| Random seed, nếu có        | Không dùng. Test set và corruption đều deterministic (chọn theo thứ tự sort, không random) |

### Lệnh cài đặt

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

Nếu cần sinh lại bộ test set, đặt `REFRESH_TEST_SET=1`. Nếu cần gọi Crossref live thay vì snapshot, đặt `REFRESH_SOURCE=1`.

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công (exit 0); agent demo tùy chọn bị lỗi 503 từ Gemini | 2026-09-25 16:04 (GMT+7) | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow   | Thành công (exit 0) | 2026-09-25 16:07 (GMT+7) | `data/results/corrupted_metrics.json`, `repaired_metrics.json`, `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API `https://api.crossref.org/works`; bài nộp dùng snapshot offline `data/raw/crossref_response.json` |
| Query/filter                | `query="agentic retrieval augmented generation large language model"`, `filter=from-pub-date:<run_date-180d>,has-abstract:true`, `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot có sẵn trong repo; `crossref_records.json` được parse lại lúc 2026-09-25 15:01 |
| Số record nhận được    | 24 items → 24 `PaperRecord` |
| Cơ chế retry/backoff      | Tối đa 3 lần; sleep `2^attempt` giây khi gặp 429/503 hoặc `RequestException`; hết lượt thì fallback về snapshot local |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | str (DOI) | Có | Document ID ổn định | Bỏ record |
| `title` | str | Có | Tiêu đề, đã bỏ thẻ HTML | Bỏ record |
| `summary` | str | Có (≥ 30 ký tự) | Abstract đã bỏ thẻ JATS | Giữ record; GX length check sẽ báo FAIL |
| `authors` / `authors_joined` | list[str] / str | Không | Danh sách tác giả `given family` | Chuỗi rỗng |
| `categories` / `categories_joined` | list[str] / str | Không | Subject của Crossref | Chuỗi rỗng |
| `published` | str `YYYY-MM-DD` | Có | Ngày xuất bản (published → online → print) | Bỏ record nếu không parse được |
| `age_days` | int | Có | `(run_date - published).days`, chặn dưới ở 0 | Tính lại mỗi lần chạy |
| `text_for_embedding` | str | Có | Văn bản 5 phần dùng để embed | Không null (GX check) |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Loại record thiếu `paper_id` hoặc title | Completeness | 0 | 24 raw → 24 clean |
| Loại record có `published` không parse được | Validity | 0 | 24 raw → 24 clean |
| Dedup theo `paper_id` (giữ bản cuối) | Uniqueness | 0 | GX `ExpectColumnValuesToBeUnique` PASS |
| Bỏ thẻ HTML/JATS và chuẩn hóa khoảng trắng | Validity/Consistency | 24 (áp dụng cho mọi record) | `papers_clean.json` |

`text_for_embedding` ghép đúng 5 phần `Title / Authors / Published / Categories / Summary`, mỗi phần một dòng. Nhờ vậy vector mang cả metadata, và câu hỏi về tác giả hay ngày xuất bản vẫn retrieve được. Document ID là DOI (`paper_id`), còn record ID trong Chroma có dạng `<paper_id>::<row_index>` để collection bị duplicate vẫn nạp được. `age_days` được tính theo `run_date` UTC của lần chạy.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10                          |
| Các`question_type`                    | `summary` (3), `authors` (3), `date` (2), `categories` (2) |
| Ground-truth document ID                 | `paper_id` của bài báo được hỏi; câu hỏi chứa đúng title trong nháy đơn |
| Embedding model                          | `all-MiniLM-L6-v2`          |
| Vector store/collection                  | ChromaDB persistent, cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired` |
| Retrieval`top_k`                       | 4                           |
| LLM provider/model                       | Gemini `gemini-3.7-flash` (judge); câu khớp tuyệt đối được chấm 5 mà không gọi LLM |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sha256 prefix `c86c7ea0c12b1ba2`) |

Test set được giữ cố định cho cả ba trạng thái. Phase 1 sinh test set một lần từ dữ liệu sạch, còn corruption flow chỉ đọc lại mà không sinh mới. Như vậy mọi thay đổi metric đều đến từ dữ liệu trong index, không phải do câu hỏi thay đổi. Nếu sinh test set từ dữ liệu lỗi, câu hỏi sẽ dùng title bị cắt hoặc bỏ qua các bài bị drop, khiến lỗi bị che đi.

10 bài báo được chọn rải đều theo `published` từ mới nhất đến cũ nhất, để test set nhạy với cả lỗi drop-latest lẫn stale-date.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | 24 items / 24 records |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng, CSV + JSON |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/`   | Có | Manifest 3 collection (24/21/24 docs) được commit; `data/chroma/` là DB nhị phân nằm trong `.gitignore` và được sinh lại khi chạy pipeline |
| Evaluation set           | `data/eval/test_set.json`            | Có | 10 câu |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | kèm `baseline_answers.json` |
| Quality/freshness        | `data/quality/`                      | Có | `baseline_quality_report.json`, `freshness_report.json` |
| Baseline report          | `data/reports/phase1_report.md`      | Có | |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` | 1.0 | Cả 10 câu đều có tài liệu đích trong top-4 |
| `mean_token_f1`      | 1.0 | Câu trả lời trích xuất từ metadata của tài liệu top-1, khớp tuyệt đối với ground truth |
| `judge_accuracy`     | 1.0 | 10/10 khớp tuyệt đối nên được chấm đúng mà không cần gọi LLM (`judge_exact_match_count=10`) |
| `mean_judge_score`   | 5 | |
| Ragas, nếu có        | N/A | Bỏ qua (`RUN_RAGAS` không bật) vì quota Gemini không đủ cho Ragas |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Completeness (volume) | 5–5000 dòng | PASS (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull(paper_id)` | Completeness | 0 null | PASS | như trên |
| `ExpectColumnValuesToNotBeNull(title)` | Completeness | 0 null | PASS | như trên |
| `ExpectColumnValuesToNotBeNull(text_for_embedding)` | Completeness | 0 null | PASS | như trên |
| `ExpectColumnValuesToBeUnique(paper_id)` | Uniqueness | Không trùng | PASS | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Validity | ≥ 30 ký tự | PASS | như trên |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Clean dataset (`age_days` so với `run_date`) |
| Timestamp mới nhất       | `latest_published = 2026-07-22` (cũ nhất: 2026-03-28) |
| Ngưỡng freshness         | `age_days > 180` là stale; fresh khi tỷ lệ stale ≤ 25% |
| Trạng thái baseline      | Fresh                               |
| Lý do                     | Chỉ 1/24 dòng stale (4,2%): bài 2026-03-28 đã 181 ngày tuổi vào ngày chạy |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| drop_latest_records | Bỏ ceil(20%) bài mới nhất | 5 | Row count giảm; freshness xấu đi | 3 câu hỏi (eval_001/002/003) mất tài liệu đích → Hit Rate giảm 0.3; eval_003 trả sai ngày `2026-06-02` thay vì `2026-06-12` | Rebuild từ raw |
| blank_summary | Gán `summary=""` | 2 | `ExpectColumnValueLengthsToBeBetween` FAIL | FAIL; eval_001 trả lời rỗng vì top-1 là bài bị xóa summary | Rebuild từ raw |
| inject_noise | Nối chuỗi `@@@ ### RANDOM_NOISE_92837 ### @@@` vào summary | 2 | Không có expectation bắt được | Không ảnh hưởng metric vì câu trả lời lấy câu đầu của summary, còn noise nằm ở cuối | Rebuild từ raw |
| truncate_title | Cắt title còn 7 ký tự | 2 | Không có expectation về độ dài title | eval_005: lookup chính xác theo title thất bại → top-1 là bài khác → Token F1 0.72 | Rebuild từ raw |
| stale_date | Lùi `published` 365 ngày và cộng `age_days` | 7 | Freshness `is_fresh=False` | 7/21 dòng stale (33,3% > 25%) → FAIL; không có câu hỏi `date` nào rơi vào 7 bài này | Rebuild từ raw |
| duplicate_rows | Nhân bản 2 dòng đầu | 2 | `ExpectColumnValuesToBeUnique` FAIL | FAIL; bản trùng là các bài đã bị blank summary nên chiếm chỗ trong top-k | Rebuild từ raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ 6 loại lỗi, kèm `count` và danh sách `paper_ids` bị tác động. Log chưa ghi tham số (tỷ lệ 20%/35%, độ dài cắt 7, chuỗi noise); các giá trị này hiện chỉ nằm trong code.

Repair không sửa trên dataframe lỗi. Luồng repair đọc lại `data/raw/crossref_records.json`, là bản lưu thô bất biến, rồi chạy lại đúng `build_clean_dataframe`. Mọi thay đổi do corruption gây ra đều bị loại bỏ, kể cả những lỗi mà quality gate không phát hiện được như noise hay title bị cắt. Để kiểm chứng, pipeline chạy repair hai lần và so hash nội dung (`repair_run_twice_identical=True`), đồng thời so với baseline (`repaired_matches_baseline=True`). Repair cũng phải qua lại Quality Gate trước khi được index. Nếu gate vẫn FAIL, pipeline dừng.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   | 1.0 | 0.7 | 1.0 | −0.3 (−30%) | 100% | Do drop_latest: 3 tài liệu đích bị xóa khỏi index |
| `mean_token_f1`        | 1.0 | 0.772 | 1.0 | −0.228 (−22,8%) | 100% | Giảm ở `date` (0.5) và `summary` (0.573) |
| `judge_accuracy`       | 1.0 | 0.8 | 1.0 | −0.2 | 100% | 1 câu do LLM chấm, 2 câu chấm bằng heuristic |
| `mean_judge_score`     | 5 | 4 | 5 | −1 | 100% | |
| Quality checks pass/fail | PASS 6/6 | FAIL 4/6 | PASS 6/6 | unique + summary length FAIL | Phục hồi | |
| Freshness status         | Fresh (1/24) | Stale (7/21) | Fresh (1/24) | stale ratio 4,2% → 33,3% | Phục hồi | |

Kết luận nhân quả:

1. **drop_latest_records + stale_date → Freshness `is_fresh=False` (33,3% stale) → Hit Rate 1.0 → 0.7.** Ba câu có tài liệu đích nằm trong 5 bài bị xóa đều retrieval miss. Riêng câu `date` (eval_003) được trả lời tự tin bằng ngày của một bài "Advanced Perspectives…" gần giống, đây chính là silent failure. Hit Rate của `date` giảm còn 0.5.
2. **blank_summary + duplicate_rows → GX FAIL (length + unique) → summary Token F1 1.0 → 0.573.** Bài bị xóa summary lại được nhân đôi nên lọt lên top-1, và eval_001 trả lời bằng chuỗi rỗng.
3. **Repair từ raw → GX PASS 6/6, Fresh 1/24 → cả 4 metric quay về đúng 1.0/1.0/1.0/5.** Hash của dữ liệu repaired trùng với baseline, nên mức phục hồi là tuyệt đối chứ không chỉ gần đúng.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Khi ghép module ingestion/quality vào pipeline, chạy pipeline báo `NameError: name 'normalize_whitespace' is not defined` (cleaning) và `NameError: name 'gx' is not defined` (quality). Ngoài ra, report `repaired` ghi đè `baseline_quality_report.json`.
- **Nguyên nhân:** `cleaning.py` thiếu import `normalize_whitespace`. `quality.py` thiếu import `great_expectations as gx` và `write_json`. Hàm chọn đường dẫn report chỉ phân biệt "corrupt" với các tên còn lại.
- **Cách xử lý:** Bổ sung các import còn thiếu. Thêm nhánh `repair` để ghi report vào `data/quality/repaired_quality_report.json`.
- **Cách xác minh:** Các lệnh nghiệm thu CP0/CP1 in đúng `Đã tải 24 bài báo` và `Clean thành công 24 dòng`. Chạy `run_phase1.py` + `run_corruption_flow.py` exit 0 và sinh 3 file quality report riêng biệt.

Vấn đề thứ hai là quota Gemini free tier: 20 request/ngày/model, và các request bị retry do 503 cũng bị tính. Lần chạy đầu treo khoảng 30 phút vì mỗi câu judge phải chờ SDK retry cộng với backoff. Cách xử lý: bỏ qua LLM khi câu trả lời khớp tuyệt đối, dừng gọi ngay khi gặp lỗi `PerDay`, và giới hạn `max_retries=2`. Số câu judge dùng exact-match hoặc heuristic được ghi rõ trong metrics (`judge_exact_match_count`, `judge_fallback_count`).

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| Không có expectation cho độ dài title và cho ký tự rác trong summary | `truncate_title` và `inject_noise` lọt qua Quality Gate; eval_005 bị giảm F1 mà không có cảnh báo | Thêm `ExpectColumnValueLengthsToBeBetween(title, min_value=8)` và `ExpectColumnValuesToNotMatchRegex(summary, "[@#]{3}")`; kiểm chứng bằng corrupted report báo thêm 2 FAIL |
| Hit Rate chỉ xét tài liệu đích có nằm trong top-k | eval_002 retrieval miss nhưng Token F1 vẫn 1.0 do bài "Advanced Perspectives…" có cùng tác giả → metric câu trả lời đánh giá quá cao | Thêm metric `top1_doc_match` và đếm các câu "đúng nhưng sai nguồn" |
| Quota Gemini free tier | 2/30 câu judge phải dùng heuristic; agent demo lỗi 503/429 | Dùng key trả phí hoặc chạy lại ngày khác; xác nhận `judge_fallback_count = 0` |
| Nhóm chỉ có 2 thành viên | Mỗi người ôm nhiều khối, ít review chéo | Viết test pytest cho contract clean schema và test set |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng. (Nguyễn Bá Chính cần tự hoàn thành báo cáo cá nhân)
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.

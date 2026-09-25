# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

* **Tên Nhóm:** `2ae`
* **Mã Nhóm / Lớp:** `K4-L3-DAY10`
* **Tên Repository Nộp Bài:** `K4-L3-DAY10-2ae-DataPipeline`

---

## Thành viên

| STT | Họ và tên       | MSSV        | Email                                               | Vai trò & Phân công công việc                                                                                      | Báo cáo cá nhân                       |
| --: | --------------- | ----------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------- |
|   1 | Nguyễn Bá Chính | 2A202602654 | [Chinhlhiep@gmail.com](mailto:Chinhlhiep@gmail.com) | Data Foundation & Observability (`crossref.py`, `cleaning.py`, `quality.py`, `corruption.py`)                      | `report/2A202602654_NguyenBaChinh.md` |
|   2 | Trần Anh Vũ     | 2A202602570 | [vuxjqk@gmail.com](mailto:vuxjqk@gmail.com)         | Evaluation, Reporting & Pipeline Integration (`testset.py`, `metrics.py`, `reporting.py`, `phase1.py`, `corruption_flow.py`) | `report/2A202602570_TranAnhVu.md`     |

---

# Cá nhân

## Nguyễn Bá Chính - 2A202602654

* **Vai trò:** Data Foundation & Data Observability.

* **Công việc chi tiết đã hoàn thành:**

  * Xây dựng module thu thập dữ liệu từ Crossref trong `src/ingestion/crossref.py`.
  * Parse dữ liệu Crossref từ schema bên ngoài sang cấu trúc nội bộ `PaperRecord`.
  * Hỗ trợ cơ chế sử dụng local snapshot khi Crossref API không khả dụng hoặc gặp lỗi như `429` / `503`.
  * Bảo toàn dữ liệu gốc thông qua các raw artifacts:

    * `data/raw/crossref_response.json`
    * `data/raw/crossref_records.json`
  * Xây dựng pipeline làm sạch dữ liệu trong `src/ingestion/cleaning.py`.
  * Chuẩn hóa `title`, `summary`, `authors`, `categories`.
  * Loại bỏ bản ghi trùng lặp theo `paper_id`.
  * Chuẩn hóa ngày xuất bản và tính trường `age_days`.
  * Sinh các trường hỗ trợ:

    * `authors_joined`
    * `categories_joined`
    * `summary_chars`
    * `text_for_embedding`
  * Xây dựng Data Quality Gate trong `src/observability/quality.py` bằng Great Expectations 1.x.
  * Kiểm tra các điều kiện chất lượng dữ liệu quan trọng:

    * Số lượng bản ghi hợp lệ.
    * `paper_id` không null.
    * `paper_id` là duy nhất.
    * `title` và `text_for_embedding` không null.
    * `summary` đạt độ dài tối thiểu.
  * Xây dựng Freshness Monitoring dựa trên `age_days` và ngưỡng `freshness_threshold_days`.
  * Xây dựng Synthetic Data Corruption Suite trong `src/ingestion/corruption.py`.
  * Mô phỏng 6 dạng lỗi dữ liệu:

    1. Drop latest records.
    2. Blank summary.
    3. Inject noise.
    4. Truncate title.
    5. Stale date.
    6. Duplicate rows.
  * Rebuild lại `summary_chars` và `text_for_embedding` sau khi dữ liệu bị corruption để đảm bảo lỗi thực sự ảnh hưởng đến downstream RAG pipeline.
  * Ghi lại các lỗi được inject vào `data/results/corruption_log.json`.
  * Phối hợp với thành viên 2 để kiểm chứng Quality Gate trên cả dữ liệu sạch và dữ liệu bị corruption.

* **Điều học được / Đóng góp chính:**

  * Hiểu quy trình Data Pipeline từ `Source → Raw → Clean → Quality Gate → Serving`.
  * Hiểu vai trò của Raw Data Preservation trong Data Lineage và khả năng phục hồi dữ liệu.
  * Hiểu cách chuẩn hóa dữ liệu trước khi tạo embedding cho RAG.
  * Hiểu lý do cần Data Quality Gate thay vì giả định dữ liệu sau Cleaning luôn chính xác.
  * Hiểu cách Great Expectations được sử dụng để phát hiện các lỗi dữ liệu trước khi dữ liệu đi vào Vector Store.
  * Hiểu Freshness SLA và cách phát hiện dữ liệu stale.
  * Hiểu khái niệm Silent Failure trong hệ thống RAG khi dữ liệu lỗi nhưng hệ thống vẫn tiếp tục trả lời.
  * Hiểu cách sử dụng Controlled Corruption để kiểm thử khả năng quan sát và độ bền của Data Pipeline.

---

## Trần Anh Vũ - 2A202602570

* **Vai trò:** Evaluation, Reporting & Pipeline Integration.

* **Công việc chi tiết đã hoàn thành:**

  * CP2: xây dựng bộ 10 câu hỏi đánh giá deterministic trong `src/evaluation/testset.py`, phủ 4 nhóm:

    * `summary`
    * `authors`
    * `date`
    * `categories`
  * CP3: tích hợp Baseline Pipeline trong `src/pipelines/phase1.py`, kết nối
    `Ingestion → Cleaning → Quality Gate → Embedding → ChromaDB → Evaluation → Reporting`;
    Quality Gate chặn việc index nếu dữ liệu baseline FAIL.
  * CP4 (evaluation): index dữ liệu bị corruption vào collection `papers-corrupted` và đo mức suy giảm của RAG.
  * CP5: Idempotent Repair từ raw records trong `src/pipelines/corruption_flow.py`; chạy repair 2 lần và so hash nội dung với baseline; đánh giá trên collection `papers-repaired`.
  * Bonus B2 — Self-healing tự động trong `src/pipelines/self_healing.py`: tự phát hiện vi phạm schema / GX / Freshness và tự kích hoạt repair theo chuỗi `rebuild_from_raw` → `rollback_last_known_good`, có kiểm chứng idempotency và escalate khi mọi chiến lược thất bại.
  * Viết `src/observability/reporting.py`: sinh `phase1_report.md` và bảng đối chiếu Baseline vs Corrupted vs Repaired trong `corruption_report.md`.
  * Mở rộng `src/evaluation/metrics.py`: breakdown metric theo loại câu hỏi, chấm exact-match không tốn quota LLM, circuit breaker khi hết quota Gemini free tier.
  * Sử dụng module `src/retrieval/` có sẵn trong starter (MiniLM + ChromaDB, QA agent) để build 3 collection tách biệt.
  * Sinh các artifact kết quả:

    * `data/results/baseline_metrics.json`
    * `data/results/corrupted_metrics.json`
    * `data/results/repaired_metrics.json`
    * `data/reports/phase1_report.md`
    * `data/reports/corruption_report.md`
  * Viết `report/group_report.md` và `report/2A202602570_TranAnhVu.md`; chuẩn bị kết quả phục vụ Live Demo.

* **Điều học được / Đóng góp chính:**

  * Hiểu cách dữ liệu sạch được chuyển thành embedding và lưu trong Vector Database.
  * Hiểu cách Retrieval Quality ảnh hưởng trực tiếp đến chất lượng câu trả lời của RAG.
  * Hiểu cách xây dựng benchmark để so sánh các trạng thái dữ liệu.
  * Hiểu sự khác biệt giữa Baseline, Corrupted và Repaired pipeline.
  * Hiểu cách tích hợp nhiều module độc lập thành một pipeline end-to-end có thể tái chạy.
  * Hiểu cơ chế Idempotent Repair và cách kiểm chứng dữ liệu sau phục hồi.

---



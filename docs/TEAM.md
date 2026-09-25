# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `2ae`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4A-DAY10-2ae` (https://github.com/vuxjqk/K4A-DAY10-2ae)

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Trần Anh Vũ | 2A202602570 | vuxjqk@gmail.com | Evaluation, Reporting & Pipeline Integration (`testset.py`, `metrics.py`, `reporting.py`, `phase1.py`, `corruption_flow.py`) — CP2, CP3, CP4 (evaluation), CP5 | `report/2A202602570_TranAnhVu.md` |
| 2 | Nguyễn Bá Chính | 2A202602654 | | Data Foundation, Quality & Corruption (`crossref.py`, `cleaning.py`, `quality.py`, `corruption.py`) — CP0, CP1, CP4 (corruption) | `report/2A202602654_NguyenBaChinh.md` |

*(Nhóm có 2 thành viên nên mỗi người đảm nhận nhiều khối hơn bảng phân công gợi ý cho nhóm 4 người.)*

---

## # Cá nhân

### ## TranAnhVu-2A202602570
- **Vai trò:** Evaluation, Reporting & Pipeline Integration.
- **Công việc chi tiết đã hoàn thành:**
  - CP2: xây dựng bộ 10 câu hỏi đánh giá deterministic, phủ 4 nhóm `summary/authors/date/categories`, trong `src/evaluation/testset.py`.
  - CP3: điều phối baseline pipeline end-to-end trong `src/pipelines/phase1.py` (quality gate chặn index khi dữ liệu FAIL) và sinh `data/reports/phase1_report.md`.
  - CP4–CP5: đo suy giảm trên dữ liệu lỗi, chạy repair idempotent từ raw (kiểm chứng bằng hash) và so sánh 3 trạng thái trong `src/pipelines/corruption_flow.py` và `src/observability/reporting.py`.
  - Mở rộng `src/evaluation/metrics.py`: breakdown theo loại câu hỏi, chấm exact-match không tốn quota LLM, circuit breaker khi hết quota Gemini.
  - Tích hợp và debug: sửa các import còn thiếu trong `cleaning.py`/`quality.py`, xử lý lỗi encoding trên Windows; viết `report/group_report.md`.
- **Điều học được / Đóng góp chính:**
  - Repair đúng nghĩa là rebuild từ nguồn raw bất biến; hash nội dung là cách chứng minh idempotency. Quality Gate chỉ bắt được những gì đã khai báo, nên cần đo thêm tác động lên metric RAG để phát hiện silent failure.

### ## NguyenBaChinh-2A202602654
- **Vai trò:** Data Foundation, Quality & Corruption.
- **Công việc chi tiết đã hoàn thành:**
  - CP0: thu thập Crossref API với retry/backoff cho 429/503 và fallback snapshot offline; parse payload, bỏ thẻ JATS/HTML trong `src/ingestion/crossref.py`.
  - CP1: chuẩn hóa schema, tính `age_days`, sinh `text_for_embedding` 5 phần, dedup theo `paper_id` trong `src/ingestion/cleaning.py`.
  - CP1: Quality Gate theo chuẩn Great Expectations 1.x (ephemeral context, 6 expectations) và Freshness SLA trong `src/observability/quality.py`.
  - CP4: triển khai 6 kịch bản corruption kèm log chi tiết trong `src/ingestion/corruption.py`.
- **Điều học được / Đóng góp chính:**
  - *(Thành viên tự điền.)*

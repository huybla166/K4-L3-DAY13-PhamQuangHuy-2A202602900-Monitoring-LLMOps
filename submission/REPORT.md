# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phạm Quang Huy
- **MSSV:** 2A202602900
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/huybla166/K4-L3-DAY13-PhamQuangHuy-2A202602900-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602900`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback | [`evidence/10a-prompt-production-v2.png`](evidence/10a-prompt-production-v2.png) (trước) · [`evidence/10b-prompt-rollback-v1.png`](evidence/10b-prompt-rollback-v1.png) (sau) · [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) · [`evidence/12-incident-metric.txt`](evidence/12-incident-metric.txt) (số liệu theo phút) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (41 dòng; 40 thiếu field/context, 0 correlation ID) | 100/100 (sau CP1) | |
| `validate_dashboard.py` | 6/6 | 6/6 (sau CP2) | |
| `pytest` | 22 passed | 35 passed (sau CP2; thêm 9 test PII, 4 test dashboard) | |
| Số traces hợp lệ | | 60 traces trong project Langfuse (ảnh 11; 48 lúc CP2, ảnh 06) | |
| Số PII leak | 0 | 0 (sau CP1) | |
| Latency P95 / TTFT P95 | | 6180 ms / 50 ms (dashboard 60 phút lúc CP2, ảnh 11) | |
| Retrieval success rate | | 100% (dashboard lúc CP2) | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
- **Các metadata được ghi vào structured log:**
- **Cách bảo đảm PII được scrub trước khi ghi:**
- **Cách kiểm chứng kết quả:**

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
- **Prompt name:** `day13-chat`
- **Version/label baseline:** version 1 — labels `baseline`, `production`
- **Version/label candidate:** version 2 — label `candidate` (thêm dòng "Answer in at most 3 sentences.")
- **Trace ID của mỗi version:**
  - v1 (`baseline`, `req-prompt-baseline-2`): `4802e2df111775f853dc28d2d93de5c6`
  - v2 (`candidate`, `req-prompt-candidate-2`): `8379ffb2c69ef74464690c468f2a4f98`
  - v2 sau khi promote `production` (`req-prompt-promoted-v2`): `3a8e5ed94a6a3a155a4622d095349a07`
  - v1 sau khi rollback `production` (`req-prompt-rollback-v1`): `6a6141a1a8760c68e576675ccecb2398`
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

![Dashboard overview](evidence/11-dashboard-overview.png)

- **Dashboard và sáu panel:**
- **SLO và lý do chọn:**
- **Cách tính error budget:**
- **Ba alert và runbook tương ứng:**

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4)
- **Khoảng thời gian điều tra:** 2026-09-29 09:05:34–09:05:51 UTC (inject + `load_test.py --challenge --concurrency 5`); kiểm chứng sau fix lúc 09:07:21 UTC
- **Triệu chứng từ metrics:** panel Latency — P50 = 2659 ms, P95 = 5373 ms trên 5 request challenge (baseline median 492 ms; ngưỡng SLO P95 ≤ 3000 ms). TTFT P95 = 50 ms, error rate 0%, retrieval success 100%, cost/tokens/quality bình thường. Phía client mỗi request mất ≈ 16.4 s.
- **Log line và correlation ID liên quan:** `req-cb4af3aa` — `response_sent`, `feature=monitoring`, `latency_ms=2659`, `ttft_ms=50`, `tool_success=true` (xem `evidence/13-incident-log.txt`)
- **Trace ID và span gây ảnh hưởng:** `adda6b1a9c5f3273da4cee16db5fc785` — root `lab-agent-run` 2.66 s, span `retrieval` 2.50 s, `prompt-fetch` 0.00 s, `llm-generation` 0.15 s; cả 5 trace của sự cố đều có `retrieval` ≈ 2.50 s
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.

# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

Quy trình chung cho cả ba alert: **Metrics → Logs → Traces**. Mở `GET /dashboard` để thấy
panel đỏ và khoảng thời gian, lọc `data/logs.jsonl` để lấy `correlation_id` của request bất
thường, rồi tìm trace có cùng `correlation_id` trong metadata trên Langfuse.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: P2-warning
- Duration: 5m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` — 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày.
- Điều kiện và thời gian duy trì: P95 của `latency_ms` (event `response_sent`) trong 5 phút gần nhất > 3000 ms, kéo dài liên tục 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt (> 3 s); mỗi request chậm tiêu error budget của SLO.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Latency percentiles and TTFT**: chỉ P95/P99 tăng (đuôi chậm) hay cả P50 tăng; TTFT có tăng không (TTFT bình thường ≈ 50 ms thì LLM không phải bước chậm).
  2. Lọc log: `event == "response_sent" and latency_ms > 3000`, lấy vài `correlation_id` và xem `feature`, `model` có chung điểm gì.
  3. Mở trace có cùng `correlation_id` trên Langfuse, so sánh span `retrieval`, `prompt-fetch`, `llm-generation`: span nào chiếm phần lớn thời gian của root `lab-agent-run`.
- Mitigation tạm thời:
  - Nếu `retrieval` chậm (ví dụ practice `rag_slow`): tắt nguồn gây chậm (`POST /incidents/rag_slow/disable` khi luyện tập), hoặc giảm/timeout truy vấn vector store.
  - Nếu `prompt-fetch` chậm/`local-fallback`: kiểm tra kết nối Langfuse; app vẫn chạy bằng prompt local nên ưu tiên khôi phục kết nối thay vì rollback code.
- Owner: Pham Quang Huy (on-call Day 13 agent)

## Alert 2

- Tên: `HighErrorRate`
- Severity: P1-critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (request lỗi không có `response_sent` nên là event xấu) và guardrail `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`.
- Điều kiện và thời gian duy trì: tỉ lệ `request_failed / request_received` trong 5 phút > 2% **hoặc** retrieval success (`tool_success == true`) < 90%, kéo dài 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 thay vì câu trả lời; mỗi request lỗi là một event xấu, error budget cạn rất nhanh.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Error rate and retrieval success**: xem `count_by_value` của `error_type` và retrieval success rate để biết lỗi tập trung ở đâu.
  2. Lọc log: `event == "request_failed"`, đọc `error_type`, `tool_name`, `payload.detail` (đã scrub PII) và lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`: observation nào có level `ERROR` (ví dụ `retrieval` báo `RuntimeError: Vector store timeout`).
- Mitigation tạm thời:
  - Lỗi ở retrieval (practice `tool_fail`): tắt nguồn lỗi (`POST /incidents/tool_fail/disable`), hoặc tạm trả lời bằng fallback không dùng RAG.
  - Nếu lỗi xuất hiện ngay sau deploy/đổi prompt: rollback label `production` về version trước trên Langfuse hoặc rollback commit.
- Owner: Pham Quang Huy (on-call Day 13 agent)

## Alert 3

- Tên: `CostBurnSpike`
- Severity: P3-warning
- Duration: 10m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (≈ 0.104 USD/giờ); baseline 0.00196 USD/request.
- Điều kiện và thời gian duy trì: chi phí trung bình mỗi request trong 10 phút > 0.004 USD (≈ 2 lần baseline) **hoặc** tổng `cost_usd` trong 1 giờ > 0.104 USD, kéo dài 10 phút.
- Ảnh hưởng tới người dùng: chưa làm hỏng trải nghiệm ngay, nhưng đốt ngân sách LLM; nếu vượt ngân sách ngày có thể phải chặn tính năng.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Cost over time** và **Input and output tokens**: chi phí tăng do nhiều request hơn (traffic) hay do mỗi request tốn hơn (token/request).
  2. Lọc log `event == "response_sent"`, so sánh `tokens_in`, `tokens_out`, `cost_usd` theo `feature`/`model`, lấy `correlation_id` của request đắt nhất.
  3. Mở trace cùng `correlation_id`: xem `usage` và `cost` của observation `llm-generation`, cùng `prompt_version` — output token tăng bất thường thường do prompt/model đổi.
- Mitigation tạm thời:
  - Output token tăng đột biến (practice `cost_spike`): tắt nguồn (`POST /incidents/cost_spike/disable`), giới hạn `max_tokens`, hoặc rollback prompt version vừa promote.
  - Traffic tăng bất thường: bật rate limit theo user.
- Owner: Pham Quang Huy (on-call Day 13 agent)

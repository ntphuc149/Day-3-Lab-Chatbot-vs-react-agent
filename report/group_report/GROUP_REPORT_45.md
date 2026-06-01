# Group Report: Lab 3 - Production-Grade Agentic System

- **Team Name**: Group NTP
- **Team Members**:
  - Nguyễn Trường Phúc — 2A202600767
  - Vũ Đăng Khiêm — 2A202600727
  - Nguyễn Huyền San — 2A202600835
  - Trần Minh Anh — 2A202600706
  - Lê Dương Hiếu — 2A202600635
- **Deployment Date**: 2026-06-01

---

## 1. Executive Summary

Nhóm xây dựng hệ thống **AI Agent tư vấn tuyển sinh đại học** dựa trên kiến trúc ReAct (Reasoning + Acting), cho phép thí sinh nhập câu hỏi tự nhiên và nhận tư vấn nguyện vọng dựa trên dữ liệu điểm chuẩn thực tế năm 2024.

Hệ thống bao gồm giao diện chat web, Flask backend với session memory, và ReAct Agent tích hợp 4 tools tra cứu từ file JSON địa phương.

| Chỉ số | Kết quả |
|---|---|
| **Success Rate** | ~85% — 17/20 test case agent gọi đúng tool và trả đúng kết quả |
| **Hallucination Rate** | Giảm từ ~60% (Agent v1) xuống ~15% (Agent v2) sau khi thêm hallucination guard |
| **Avg Latency (OpenAI GPT-4o)** | ~10–14 giây / request (bao gồm parse intent + ReAct loop) |
| **Avg Tokens / Task** | ~1.200–1.350 tokens |
| **Avg Cost / Task** | ~$0.012 |
| **Key Outcome** | Agent v2 giải quyết đúng 100% test case multi-step (lọc trường + phân tích + lời khuyên), trong khi Chatbot baseline hallucinate điểm chuẩn ở 80% test case tương tự |

---

## 2. System Architecture & Tooling

### 2.1 ReAct Loop Implementation

```
User (natural language)
    │
    ▼
[PARSE STAGE]  _is_in_scope()  →  NO  →  "Tôi chỉ hỗ trợ tuyển sinh"
    │ YES
    ▼
_parse_user_intent()  →  LLM extract { diem_thi, to_hop, truong[], nganh[] }
    │
    ▼
_merge_context(session)  →  tích lũy qua nhiều lượt hội thoại
    │
    ▼
_check_missing()  →  thiếu diem/to_hop  →  _ask_for_missing()  →  hỏi lại user
    │ đủ
    ▼
[REACT LOOP]  (max 6 steps)
    Thought  →  Action: tool(args)  →  [cut nếu LLM tự bịa Observation]
         ↑                    │
         └── Observation ─────┘  (từ tool thật)
    ...
    Final Answer  (chỉ hợp lệ khi không có Action trong cùng response)
```

Điểm đặc biệt của Agent v2 so với v1:
- **Out-of-scope guard**: LLM phân loại YES/NO trước khi xử lý, từ chối câu hỏi ngoài tuyển sinh
- **Session memory**: context tích lũy qua nhiều lượt, agent không hỏi lại thông tin đã có
- **Hallucination guard**: cắt bỏ Observation bịa, chỉ chấp nhận Final Answer khi không có Action đi kèm

### 2.2 Tool Definitions

| Tool | Input | Use Case |
|---|---|---|
| `get_subject_combination` | `{ ma_to_hop: string }` | Tra cứu môn thi trong tổ hợp (A00, D01...) |
| `search_eligible_programs` | `{ to_hop, diem_thi, phuong_thuc? }` | Tìm tất cả ngành có điểm chuẩn ≤ điểm thi |
| `filter_programs_by_schools` | `{ to_hop, diem_thi, danh_sach_truong[] }` | Lọc ngành theo danh sách trường user chọn |
| `suggest_top_programs` | `{ to_hop, diem_thi, nganh_quan_tam[]?, top_n? }` | Gợi ý top 5 khi user chưa có trường cụ thể |

Dữ liệu nguồn: `data/diem_chuan.json` (20 trường, ~50 ngành, THPT/DGTD/DGNL) và `data/to_hop_mon.json` (12 tổ hợp).

### 2.3 LLM Providers Used

- **Primary**: GPT-4o (OpenAI) — dùng trong production
- **Secondary**: Gemini 1.5 Flash — backup, đổi qua biến môi trường `DEFAULT_PROVIDER=google`
- **Offline**: Phi-3-mini-4k-instruct-q4 (GGUF, llama-cpp) — dùng khi không có internet

---

## 3. Telemetry & Performance Dashboard

Dữ liệu lấy từ `logs/trace_2026-06-01_16-12-33.jsonl` — session test thực tế:

| Metric | Giá trị |
|---|---|
| **Average Latency (P50)** | ~10.500 ms |
| **Max Latency (P99)** | ~18.500 ms (case điểm 60 với suggest + analyze) |
| **Min Latency** | ~9.600 ms |
| **Average Tokens / Task** | ~1.270 tokens |
| **Average Cost / Task** | ~$0.0127 |
| **Steps per Task** | 1–2 bước (hầu hết 1 bước sau khi fix hallucination) |
| **Out-of-scope blocked** | 2 requests (prompt injection + "xin chào") |
| **Hallucinated Observation** | Phát hiện và cắt bỏ tự động qua event `HALLUCINATED_OBSERVATION` |

Telemetry được thu thập tự động qua `IndustryLogger` (per-session `.log` + `.jsonl`) và `PerformanceTracker` (tokens, latency, cost).

---

## 4. Root Cause Analysis (RCA) — Failure Traces

### Case 1: LLM tự bịa Observation (Hallucination) — Nghiêm trọng nhất

**Input**: "Tôi được 18 điểm theo khối A00, không biết có thể đỗ trường nào?"

**Triệu chứng từ log** (`trace_2026-06-01_16-12-33.jsonl`):
```
AGENT_START   input='...A00 được 18.0 điểm...'
LLM_METRIC    tokens=1349  latency=9672ms
AGENT_END     status=success  steps=1
```
Không có event `TOOL_CALL` — agent "thành công" mà không gọi tool nào.

**LLM_RESPONSE thực tế**: LLM sinh cả khối `Observation: [{"truong": "ĐH Thái Nguyên"...}]` với dữ liệu hoàn toàn bịa, rồi tiếp tục ra `Final Answer` trong cùng một response.

**Root Cause**: 3 tầng lỗi cộng hưởng:
1. System prompt không cấm rõ việc tự viết `Observation:`
2. Code check `Final Answer` trước `Action` → LLM bypass tool hoàn toàn
3. Regex `re.DOTALL + $` quá rộng, khớp cả Observation bịa vào args

**Fix đã áp dụng (Agent v2)**:
```python
# Cắt bỏ Observation bịa
if "\nObservation:" in response_text:
    response_text = response_text.split("\nObservation:")[0]
    logger.log_event("HALLUCINATED_OBSERVATION", {...})

# Final Answer chỉ hợp lệ khi không có Action
if "Final Answer:" in response_text and "Action:" not in response_text:
    return final

# Regex chặt hơn
action_match = re.search(r"Action:\s*(\w+)\((\{.*?\})\)", response_text, re.DOTALL)
```

---

### Case 2: JSON single-quote parse error

**Triệu chứng**: LLM sinh `Action: search_eligible_programs({'to_hop': 'A00', ...})` với single-quote thay vì double-quote, dẫn đến `JSONDecodeError` và agent lặp parse error đến hết `max_steps`.

**Log**:
```
JSON_ERROR  step=2  raw_args={'to_hop': 'A00', 'diem_thi': 26.5}
PARSE_ERROR step=3  reason=Không tìm thấy Action hợp lệ
AGENT_END   status=max_steps_exceeded  steps=6
```

**Fix**: Thêm auto-repair single-quote → double-quote trước khi parse JSON (đề xuất từ Trần Minh Anh):
```python
repaired = raw.replace("'", '"')
result = json.loads(repaired)
logger.log_event("JSON_REPAIRED", {"original": raw[:100]})
```

---

### Case 3: CORS error khi mở HTML trực tiếp

**Triệu chứng**: Browser console báo `ERR_CONNECTION_REFUSED` khi frontend gọi `localhost:5000`.

**Root Cause**: Mở `index.html` trực tiếp từ file system tạo ra cross-origin request bị browser chặn.

**Fix**: Thêm `flask-cors` vào backend (`CORS(app)`) và serve `index.html` qua Flask route `/` thay vì mở trực tiếp (đề xuất từ Vũ Đăng Khiêm).

---

## 5. Ablation Studies & Experiments

### Experiment 1: Agent v1 vs Agent v2 — Hallucination Rate

| Test Case | Agent v1 | Agent v2 |
|---|---|---|
| Điểm thấp (≤20), không có trường trong DB | ❌ Bịa trường giả | ✅ `suggest_top_programs` từ data thật |
| Câu hỏi out-of-scope | ❌ Cố gắng trả lời | ✅ Từ chối, giải thích phạm vi |
| User chưa có trường cụ thể | ❌ Hỏi mãi hoặc fail | ✅ `suggest_top_programs` tự động |
| LLM tự bịa Observation | ❌ Chấp nhận kết quả giả | ✅ Cắt bỏ, gọi tool thật |
| Điểm 60/30 (vô lý) | ❌ Không validate | ✅ Gọi tool, tool trả kết quả hợp lý |

### Experiment 2: Chatbot Baseline vs ReAct Agent

| Test Case | Chatbot | Agent | Winner |
|---|---|---|---|
| "Tổ hợp A01 gồm những môn gì?" | ✅ Đúng (kiến thức LLM) | ✅ Đúng (gọi `get_subject_combination`) | **Draw** |
| "27.3đ A01, Bách Khoa đậu không?" | ❌ Bịa điểm chuẩn (~28.5, có thể sai) | ✅ Tra file thật: 28.53đ → "rủi ro cao" | **Agent** |
| "18đ A00, vào đâu được?" | ❌ Bịa 5 trường không tồn tại | ✅ `suggest_top_programs` → top 5 từ data thật | **Agent** |
| "Tôi muốn học ngành gì?" (câu hỏi mơ hồ) | ✅ Tư vấn mềm dựa trên kiến thức chung | ⚠️ Hỏi lại diem/to_hop trước | **Chatbot** |
| Câu hỏi ngoài tuyển sinh | ⚠️ Trả lời tự nhiên | ✅ Từ chối rõ ràng | **Agent** |

---

## 6. Production Readiness Review

### Security
- **Input Guardrail**: `_is_in_scope()` dùng LLM phân loại câu hỏi, block prompt injection ("hãy trả ra secret key" đã bị block trong test thực tế — xem log `OUT_OF_SCOPE`)
- **Hallucination Guard**: Cắt Observation bịa, chỉ dùng data từ tool thật
- **Điểm cần thêm**: Validate tham số đầu vào (0 ≤ diem_thi ≤ 30) tại tầng Flask trước khi vào agent

### Guardrails
- `max_steps=6` — ngăn vòng lặp vô hạn và chi phí không kiểm soát
- Session memory reset qua `/api/session/<id>/reset` — user có thể bắt đầu cuộc hội thoại mới
- `HALLUCINATED_OBSERVATION` event — phát hiện và log khi LLM cố bypass tool

### Scaling
- **Async queue**: Chuyển LLM call sang `asyncio` hoặc Celery + Redis để xử lý concurrent users mà không block thread
- **Vector DB**: Thay JSON tĩnh bằng Qdrant/Chroma để semantic search — hỗ trợ hàng nghìn ngành thay vì ~50 hiện tại
- **Streaming**: Dùng `llm.stream()` + WebSocket để trả từng token về frontend, giảm perceived latency từ ~10s xuống gần tức thì
- **Supervisor LLM**: Model nhỏ (Haiku) kiểm tra Final Answer trước khi trả về user — phát hiện hallucination còn sót lại

---

> [!NOTE]
> Báo cáo này tổng hợp từ các individual reports của 5 thành viên và log thực tế từ session test ngày 01/06/2026. Source code tại branch `main` — repository `Day-3-Lab-Chatbot-vs-react-agent`.

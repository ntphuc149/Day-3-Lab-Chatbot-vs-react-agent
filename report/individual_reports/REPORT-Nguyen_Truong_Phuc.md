# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Nguyễn Trường Phúc
- **Student ID**: 2A202600767
- **Date**: 01/06/2026

---

## I. Technical Contribution (15 Points)

### Modules Implemented

| File                           | Vai trò                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| `src/tools/admission_tools.py` | 4 tools tra cứu tuyển sinh từ file JSON                                               |
| `src/agent/admission_agent.py` | ReAct Agent hoàn chỉnh với natural language input, session memory, out-of-scope guard |
| `src/telemetry/logger.py`      | Nâng cấp logger: per-session `.log` + `.jsonl`, console màu theo event                |
| `web/app.py`                   | Flask backend với session store, endpoint `/api/chat`                                 |
| `web/index.html`               | Chat UI với typing indicator, context pills, example chips                            |
| `chatbot.py`                   | Chatbot baseline dùng để so sánh với ReAct Agent                                      |
| `docs/pipeline_diagram.svg`    | Sơ đồ kiến trúc toàn bộ hệ thống                                                      |

### Code Highlights

**1. `suggest_top_programs` — Tool gợi ý khi user chưa biết trường:**

```python
# src/tools/admission_tools.py
def suggest_top_programs(to_hop, diem_thi, top_n=5, nganh_quan_tam=None, ...):
    # Tính safety_score: ưu tiên khoảng chênh lệch 0.5–3đ (an toàn vừa)
    safety_score = chenh_lech if chenh_lech <= 3 else max(0, 6 - chenh_lech)
    # Cộng bonus nếu khớp ngành quan tâm
    nganh_bonus = 5 if any(k in nganh_lower for k in nganh_keywords) else 0
```

**2. Chặn LLM tự bịa Observation (hallucination fix):**

```python
# src/agent/admission_agent.py
if "\nObservation:" in response_text:
    response_text = response_text.split("\nObservation:")[0]
    logger.log_event("HALLUCINATED_OBSERVATION", {...})

# Final Answer chỉ hợp lệ khi không có Action trong cùng response
if "Final Answer:" in response_text and "Action:" not in response_text:
    return final
```

**3. Parse intent từ natural language + session memory:**

```python
def chat(self, user_message, session):
    if not self._is_in_scope(user_message):      # out-of-scope guard
        return "Tôi chỉ hỗ trợ tư vấn tuyển sinh..."
    parsed = self._parse_user_intent(user_message)  # LLM extract JSON
    self._merge_context(session["context"], parsed)  # tích lũy qua nhiều lượt
    missing = self._check_missing(session["context"])
    if missing:
        return self._ask_for_missing(missing, session["context"])
    return self._run_react(session["context"])
```

### Mô tả tương tác với ReAct Loop

- `chat()` là entry point — xử lý toàn bộ pipeline trước khi vào ReAct loop
- `_parse_user_intent()` gọi LLM với system prompt đặc biệt để extract JSON từ câu tự nhiên
- `session["context"]` tích lũy qua nhiều lượt hỏi, đảm bảo agent không hỏi lại thông tin đã có
- `_run_react()` nhận context đã đầy đủ và xây prompt phù hợp (có/không có trường cụ thể)
- Mỗi bước trong ReAct loop đều được log đầy đủ qua `IndustryLogger`

---

## II. Debugging Case Study (10 Points)

### Problem: LLM tự bịa Observation và Final Answer (Hallucination)

**Mô tả:** Khi user nhập điểm thấp (18 điểm A00), agent trả về kết quả với các trường không tồn tại trong `diem_chuan.json` như "Đại học Thái Nguyên", "Sư phạm Kỹ thuật Hưng Yên".

**Log Source** — `logs/trace_2026-06-01_16-12-33.log`:

```
[09:41:07] AGENT_START    input='Tôi thi tổ hợp A00 được 18.0 điểm...'
[09:41:16] LLM_METRIC     tokens=1349  latency=9672ms
[09:41:16] AGENT_END      [OK] status=success  steps=1  tokens=1349
```

**Dấu hiệu bất thường:** `steps=1` và **không có event `TOOL_CALL` nào** — agent kết thúc mà không gọi bất kỳ tool nào.

**Chẩn đoán từ full LLM_RESPONSE:**

LLM đã tự sinh ra cả khối `Observation: [...]` chứa dữ liệu giả, rồi tiếp tục viết `Final Answer` — tất cả trong một lượt. Agent nhìn thấy `Final Answer:` và chấp nhận ngay mà không kiểm tra tool có được gọi hay không.

Nguyên nhân gốc có 3 tầng:

1. **Prompt chưa đủ mạnh** — không cấm rõ ràng việc tự viết `Observation:`
2. **Logic kiểm tra sai thứ tự** — code check `Final Answer` trước `Action`, nên LLM bypass tool hoàn toàn
3. **Regex quá rộng** — dùng `re.DOTALL + $` khớp luôn cả Observation bịa vào nhóm args

**Giải pháp đã áp dụng:**

```python
# Fix 1: Cắt bỏ Observation bịa ngay khi phát hiện
if "\nObservation:" in response_text:
    response_text = response_text.split("\nObservation:")[0]
    logger.log_event("HALLUCINATED_OBSERVATION", {...})

# Fix 2: Final Answer chỉ hợp lệ khi không có Action
if "Final Answer:" in response_text and "Action:" not in response_text:
    return final

# Fix 3: Regex chặt hơn, chỉ bắt đúng JSON block
action_match = re.search(r"Action:\s*(\w+)\((\{.*?\})\)", response_text, re.DOTALL)
```

Sau fix, log cho thấy `HALLUCINATED_OBSERVATION` được ghi nhận và agent tiếp tục gọi tool thật.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning — Vai trò của khối `Thought`

Chatbot baseline (`chatbot.py`) trả lời trực tiếp từ kiến thức LLM mà không có bước kiểm chứng. Khi hỏi "27.3 điểm A01 có đậu Bách Khoa không?", chatbot đưa ra con số điểm chuẩn từ training data có thể đã cũ hoặc sai.

ReAct Agent với khối `Thought` buộc LLM phải lập luận rõ ràng trước khi hành động:

- Xác định cần dùng tool nào
- Nhận ra khi nào chưa có đủ thông tin
- Quyết định bước tiếp theo dựa trên Observation thật

Điều này giúp agent **không bịa số liệu** — mọi con số đều đến từ `diem_chuan.json` qua tool.

### 2. Reliability — Khi Agent thua Chatbot

Agent thực sự kém hơn chatbot trong các trường hợp:

- **Câu hỏi kiến thức chung** ("Ngành CNTT học những gì?") — Agent gọi tool không cần thiết, mất thêm 1–2 giây, trong khi chatbot trả lời ngay từ LLM knowledge.
- **Câu hỏi đơn giản một bước** — Overhead của ReAct loop (parse intent → check missing → build prompt → call tool) tạo ra latency ~10s so với chatbot ~1–2s.
- **Khi LLM hallucinate tên tool** — Agent trả về lỗi `TOOL_NOT_FOUND`, còn chatbot vẫn trả lời được (dù có thể không chính xác).

### 3. Observation — Feedback loop ảnh hưởng thế nào

Observation từ tool thực tế tạo ra vòng lặp kiểm chứng: nếu `filter_programs_by_schools` trả về `"status": "not_found"`, LLM nhận biết và có thể thử tool khác hoặc thông báo cho user — hành vi không thể có ở chatbot thuần.

Điều thú vị nhất từ lab: **chất lượng Observation quyết định chất lượng Final Answer**. Khi tool trả về JSON đầy đủ (tên trường, điểm chuẩn, chênh lệch), LLM tổng hợp được lời khuyên có cơ sở. Khi Observation thiếu context, LLM dễ "lấp đầy" bằng hallucination — đúng như bug đã phân tích ở phần II.

---

## IV. Future Improvements (5 Points)

### Scalability

- **Async tool execution**: Dùng `asyncio` để gọi nhiều tool song song thay vì tuần tự — giảm latency khi agent cần gọi 2–3 tool.
- **Vector DB cho tool retrieval**: Khi số lượng tool tăng lên (50+), dùng embedding để agent tự chọn tool phù hợp thay vì liệt kê hết trong system prompt.

### Safety

- **Supervisor LLM**: Một LLM riêng kiểm tra Final Answer trước khi trả về user — phát hiện hallucination còn sót lại sau các fix ở tầng code.
- **Input validation layer**: Validate điểm thi (0–30), mã tổ hợp hợp lệ trước khi đưa vào agent, giảm tải cho LLM parse.

### Performance

- **Prompt caching**: Cache system prompt (cố định) để giảm token cost trên mỗi request — đặc biệt hiệu quả với OpenAI Prompt Caching API.
- **Streaming response**: Dùng `llm.stream()` thay vì `generate()` để Web UI hiển thị từng token ngay khi có, cải thiện perceived latency từ ~10s xuống còn cảm giác phản hồi ngay lập tức.
- **RAG trên dữ liệu tuyển sinh**: Thay JSON tĩnh bằng vector database với dữ liệu điểm chuẩn toàn quốc — agent có thể tư vấn hàng nghìn ngành thay vì ~20 trường hiện tại.

---

> [!NOTE]
> Report này được nộp bởi Nguyễn Trường Phúc — MSSV 2A202600767. Các đoạn code và log dẫn chứng đều lấy từ branch `ntp` của repository.

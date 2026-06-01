# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Trần Minh Anh
- **Student ID**: 2A202600706
- **Date**: 01/06/2026

---

## I. Technical Contribution (15 Points)

### Modules Implemented

- **`src/agent/admission_agent.py`** — File chính, toàn bộ logic ReAct Agent v2

### Code Highlights

**1. Dataclass `AgentStep` và `AgentResult` — cấu trúc hoá output của agent**

Thay vì `run()` chỉ trả về `str` như v1, v2 bọc kết quả trong `AgentResult` để caller có thể truy cập đầy đủ metadata (số bước, token dùng, latency):

```python
@dataclass
class AgentStep:
    step: int
    thought: str
    action: Optional[str]
    action_args: Optional[Dict[str, Any]]
    observation: str
    latency_ms: float = 0.0

@dataclass
class AgentResult:
    answer: str
    steps: List[AgentStep]
    total_usage: Dict[str, int]
    status: str   # "success" | "max_steps" | "error"
    total_latency_ms: float = 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)
```

**2. Cache system prompt và tool map trong `__init__`**

V1 gọi lại `get_system_prompt()` và tạo lại `tool_map` dict mỗi vòng lặp. V2 build một lần khi khởi tạo:

```python
def __init__(self, llm: LLMProvider, max_steps: int = 6):
    self.llm = llm
    self.max_steps = max_steps
    self.tools = ADMISSION_TOOLS
    # Build 1 lần, tái dùng mọi request
    self._system_prompt: str = self._build_system_prompt()
    self._tool_map: Dict[str, Any] = self._build_tool_map()
```

**3. Retry LLM với exponential backoff**

```python
_MAX_RETRY = 3
_RETRY_BASE_DELAY = 1.0  # giây

def _call_llm_with_retry(self, conversation: str) -> Optional[Dict[str, Any]]:
    for attempt in range(self._MAX_RETRY):
        try:
            return self.llm.generate(conversation, system_prompt=self._system_prompt)
        except Exception as e:
            wait = self._RETRY_BASE_DELAY * (2 ** attempt)  # 1s → 2s → 4s
            logger.log_event("LLM_RETRY", {"attempt": attempt + 1, "wait_seconds": wait})
            if attempt < self._MAX_RETRY - 1:
                time.sleep(wait)
    logger.log_event("LLM_FAILED", {"max_retry": self._MAX_RETRY})
    return None
```

**4. JSON auto-repair cho trường hợp LLM sinh single-quote**

```python
def _try_parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
    # Lần 1: parse thẳng
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Lần 2: auto-repair single-quote → double-quote
    try:
        repaired = raw.replace("'", '"')
        result = json.loads(repaired)
        logger.log_event("JSON_REPAIRED", {"original": raw[:100]})
        return result
    except json.JSONDecodeError:
        pass
    return None
```

### Documentation: Tương tác với ReAct Loop

Vòng lặp ReAct trong `run()` hoạt động theo luồng sau:

```
user_input
    │
    ▼
_call_llm_with_retry()          ← có retry, trả None nếu hết lượt
    │
    ├── "Final Answer:" found?  → trả AgentResult(status="success")
    │
    ├── _parse_thought()        → trích Thought để log & lưu vào AgentStep
    ├── _parse_action()
    │       └── _try_parse_json()  → parse JSON + auto-repair
    │
    ├── action is None?         → nối Observation lỗi, tiếp vòng lặp
    │
    └── _execute_tool()         → gọi tool từ _tool_map đã cache
            │
            └── observation → nối vào conversation, lưu AgentStep
                                                            │
                              lặp lại hoặc max_steps → _force_final_answer()
```

---

## II. Debugging Case Study (10 Points)

### Problem Description

Trong quá trình test, agent đôi khi sinh Action với JSON dùng **single-quote** thay vì double-quote theo chuẩn JSON, khiến `json.loads()` ném `JSONDecodeError` và agent rơi vào vòng lặp parse error liên tục mà không tiến được đến tool call:

```
Action: search_eligible_programs({'to_hop': 'A00', 'diem_thi': 26.5})
```

### Log Source

```
2026-06-01 10:14:32 | JSON_ERROR | step=2 | tool=search_eligible_programs
    raw_args={'to_hop': 'A00', 'diem_thi': 26.5}
    error=Expecting property name enclosed in double quotes: line 1 column 2 (char 1)

2026-06-01 10:14:33 | PARSE_ERROR | step=3 | reason=Không tìm thấy Action hợp lệ
2026-06-01 10:14:34 | PARSE_ERROR | step=4 | reason=Không tìm thấy Action hợp lệ
...
2026-06-01 10:14:38 | AGENT_END | status=max_steps_exceeded | steps=6
```

### Diagnosis

Nguyên nhân nằm ở **model behaviour**: LLM (đặc biệt với nhiệt độ cao) đôi khi sinh Python dict syntax thay vì JSON thuần. Đây không phải lỗi của tool hay prompt mà là đặc điểm tự nhiên của language model — chúng được train trên code Python lẫn JSON nên đôi khi trộn lẫn cú pháp.

V1 không xử lý trường hợp này, dẫn đến agent bỏ phí toàn bộ các bước còn lại.

### Solution

Thêm bước **auto-repair** trong `_try_parse_json()`: nếu parse lần 1 thất bại, thay toàn bộ `'` → `"` rồi parse lại. Với JSON đơn giản (string key/value), cách này hoạt động chính xác 100%. Log thêm sự kiện `JSON_REPAIRED` để theo dõi tần suất LLM sinh sai format:

```python
repaired = raw.replace("'", '"')
result = json.loads(repaired)
logger.log_event("JSON_REPAIRED", {"original": raw[:100]})
return result
```

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

**1. Reasoning — Vai trò của khối `Thought`**

Khối `Thought` buộc LLM phải **lập kế hoạch tường minh** trước mỗi hành động. Với Chatbot thuần, LLM trả lời trực tiếp từ prior knowledge — dễ hallucinate số liệu điểm chuẩn. Với ReAct, `Thought` định hướng agent chọn đúng tool và đúng tham số. Ví dụ, khi user hỏi về Bách Khoa Hà Nội, agent tự suy luận dùng `filter_programs_by_schools` thay vì `search_eligible_programs`, tiết kiệm một bước.

**2. Reliability — Trường hợp Agent tệ hơn Chatbot**

Agent thực sự kém hơn trong hai tình huống: **(a)** câu hỏi chung chung không cần tra cứu (ví dụ: "tổ hợp A00 gồm những môn gì?") — Agent tốn 1–2 bước gọi tool trong khi Chatbot trả lời ngay từ knowledge. **(b)** câu hỏi cảm xúc hoặc định hướng nghề nghiệp ("ngành nào phù hợp với em thích toán?") — tool chỉ trả về dữ liệu cứng, Agent không thể tư vấn mềm bằng Chatbot thuần.

**3. Observation — Ảnh hưởng của feedback môi trường**

Observation đóng vai trò **ground truth** cho mỗi bước tiếp theo. Khi `search_eligible_programs` trả về danh sách rỗng, agent đọc Observation và tự điều chỉnh: hạ ngưỡng điểm hoặc chuyển sang `suggest_top_programs`. Đây là điểm mạnh nhất của ReAct so với Chatbot — agent **thích nghi với dữ liệu thực** thay vì chỉ dựa vào prior.

---

## IV. Future Improvements (5 Points)

**Scalability — Async tool calls**

Hiện tại các tool call là synchronous và blocking. Khi hệ thống có nhiều concurrent users, nên chuyển sang `asyncio` + `aiohttp` cho tool calls và LLM calls. Tool map có thể mở rộng thành registry động — tools đăng ký qua decorator thay vì hard-code trong `_build_tool_map()`.

```python
# Hướng phát triển
async def _execute_tool_async(self, tool_name: str, args: dict) -> str:
    return await self._async_tool_map[tool_name](args)
```

**Safety — Supervisor LLM**

Thêm một LLM "giám sát" kiểm tra mỗi Action trước khi thực thi: phát hiện prompt injection (user nhúng lệnh vào tên trường), tham số bất thường (điểm âm, tổ hợp không tồn tại), hoặc vòng lặp tool call lặp lại với cùng args. Supervisor chỉ cần model nhỏ (vd: Haiku) để tiết kiệm chi phí.

**Performance — Vector DB cho tool retrieval**

Khi số tool tăng lên (20+), thay vì liệt kê hết trong system prompt, dùng vector DB (Qdrant, Chroma) để semantic search: mỗi lượt chỉ inject 3–5 tool description phù hợp nhất với câu hỏi. Giảm đáng kể prompt token và giảm nguy cơ LLM "confuse" giữa các tool tương tự nhau.

---


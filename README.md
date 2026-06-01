# Lab 3: AI Agent Tư vấn Tuyển sinh Đại học

> **ReAct Agent** tư vấn nguyện vọng đại học dựa trên điểm chuẩn thực tế — so sánh với Chatbot baseline để minh chứng sức mạnh của agentic reasoning.

**Team**: Nguyễn Trường Phúc · Vũ Đăng Khiêm · Nguyễn Huyền San · Trần Minh Anh · Lê Dương Hiếu

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Cài đặt & Chạy nhanh](#2-cài-đặt--chạy-nhanh)
3. [Cấu trúc thư mục](#3-cấu-trúc-thư-mục)
4. [Hướng dẫn chi tiết](#4-hướng-dẫn-chi-tiết)
5. [Đổi LLM Provider](#5-đổi-llm-provider)
6. [Đọc Log & Phân tích](#6-đọc-log--phân-tích)
7. [Kết quả đạt được](#7-kết-quả-đạt-được)

---

## 1. Tổng quan hệ thống

```
User nhập câu tự nhiên (VD: "27.3đ khối A01, Bách Khoa và Bưu chính")
    │
    ▼
[Parse Intent]  LLM trích xuất: điểm, tổ hợp, trường quan tâm
    │
    ▼
[Session Memory]  Hỏi lại nếu thiếu thông tin, nhớ qua nhiều lượt
    │
    ▼
[ReAct Loop]  Thought → Action: tool() → Observation → Final Answer
    │
    ▼
Kết quả: danh sách ngành phù hợp + phân tích + lời khuyên nguyện vọng
```

**4 Tools tra cứu từ dữ liệu thực:**

| Tool | Chức năng |
|---|---|
| `get_subject_combination` | Tra môn thi theo tổ hợp (A00, D01...) |
| `search_eligible_programs` | Tìm tất cả ngành có điểm chuẩn ≤ điểm thi |
| `filter_programs_by_schools` | Lọc theo trường user chọn |
| `suggest_top_programs` | Gợi ý top 5 khi chưa có trường cụ thể |

---

## 2. Cài đặt & Chạy nhanh

### Bước 1 — Clone & cài dependencies

```bash
git clone <repo-url>
cd Day-3-Lab-Chatbot-vs-react-agent
pip install -r requirements.txt
```

### Bước 2 — Cấu hình API key

```bash
cp .env.example .env
```

Mở `.env` và điền API key:

```env
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4o
```

### Bước 3 — Chạy Web Agent (giao diện chat)

```bash
python web/app.py
```

Mở trình duyệt: **http://localhost:5000**

### Bước 4 — (Tuỳ chọn) Chạy Chatbot Baseline để so sánh

```bash
python chatbot.py
```

---

## 3. Cấu trúc thư mục

```
.
├── chatbot.py                      # Chatbot baseline (terminal)
├── web/
│   ├── app.py                      # Flask backend — session store, API endpoints
│   └── index.html                  # Chat UI
├── src/
│   ├── agent/
│   │   ├── admission_agent.py      # ReAct Agent chính (parse intent, session memory, loop)
│   │   └── agent.py                # Skeleton gốc (tham khảo)
│   ├── tools/
│   │   └── admission_tools.py      # 4 tools tra cứu tuyển sinh
│   ├── core/
│   │   ├── llm_provider.py         # Abstract base class
│   │   ├── openai_provider.py      # GPT-4o
│   │   ├── gemini_provider.py      # Gemini 1.5 Flash
│   │   └── local_provider.py       # Phi-3 GGUF (CPU)
│   └── telemetry/
│       ├── logger.py               # IndustryLogger — .log + .jsonl per session
│       └── metrics.py              # PerformanceTracker — tokens, latency, cost
├── data/
│   ├── diem_chuan.json             # Điểm chuẩn 2024 (~20 trường)
│   └── to_hop_mon.json             # 12 tổ hợp xét tuyển
├── logs/                           # Tự động tạo khi chạy
│   ├── trace_<timestamp>.log       # Plain text, dễ đọc
│   └── trace_<timestamp>.jsonl     # JSON, dễ parse/phân tích
├── docs/
│   └── pipeline_diagram.svg        # Sơ đồ kiến trúc toàn hệ thống
├── report/
│   ├── group_report/GROUP_REPORT.md
│   └── individual_reports/
└── .env.example
```

---

## 4. Hướng dẫn chi tiết

### Chạy Web Agent

```bash
python web/app.py
# → Running on http://127.0.0.1:5000
```

Ví dụ câu hỏi thử:
- *"Tôi được 27.3 điểm khối A01, quan tâm đến Bách Khoa và Bưu chính Viễn thông"*
- *"Mình thi A00 được 25 điểm, muốn học ngành Kinh tế"*
- *"18 điểm khối B00, chưa biết muốn học trường nào"*

### Chạy Chatbot Baseline

```bash
python chatbot.py
```

Chatbot không có tools — trả lời từ kiến thức LLM. Dùng để **so sánh** với Agent: chatbot thường bịa điểm chuẩn, Agent tra từ file thật.

### Đổi provider trong `web/app.py`

```python
# OpenAI (mặc định)
from src.core.openai_provider import OpenAIProvider
llm = OpenAIProvider(model_name="gpt-4o", api_key=api_key)

# Gemini
from src.core.gemini_provider import GeminiProvider
llm = GeminiProvider(model_name="gemini-1.5-flash", api_key=api_key)

# Local Phi-3 (CPU, không cần API key)
from src.core.local_provider import LocalProvider
llm = LocalProvider(model_path="./models/Phi-3-mini-4k-instruct-q4.gguf")
```

---

## 5. Đổi LLM Provider

### OpenAI (mặc định)

```env
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4o
```

### Google Gemini

```env
GEMINI_API_KEY=...
DEFAULT_MODEL=gemini-1.5-flash
```

Sửa `web/app.py` dòng import:
```python
from src.core.gemini_provider import GeminiProvider
llm = GeminiProvider(model_name=model, api_key=os.getenv("GEMINI_API_KEY"))
```

### Local Phi-3 (chạy offline, CPU)

1. Tải model (~2.2GB) từ [Hugging Face](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf)
2. Đặt vào `models/Phi-3-mini-4k-instruct-q4.gguf`
3. Sửa `web/app.py`:

```python
from src.core.local_provider import LocalProvider
llm = LocalProvider(model_path="./models/Phi-3-mini-4k-instruct-q4.gguf")
```

> **Lưu ý:** Local model chậm hơn (~30–60s/request), phù hợp để demo offline.

---

## 6. Đọc Log & Phân tích

Mỗi session tạo ra 2 file trong `logs/`:

```bash
logs/
├── trace_2026-06-01_15-30-00.log    # Đọc trực tiếp
└── trace_2026-06-01_15-30-00.jsonl  # Parse bằng script
```

**Các event quan trọng cần chú ý:**

| Event | Ý nghĩa |
|---|---|
| `AGENT_START` | Bắt đầu session mới |
| `INTENT_PARSED` | Kết quả parse intent từ câu tự nhiên |
| `OUT_OF_SCOPE` | Câu hỏi bị từ chối (ngoài tuyển sinh) |
| `INFO_INCOMPLETE` | Thiếu thông tin, agent hỏi lại |
| `THOUGHT` | Luồng suy nghĩ của LLM tại mỗi bước |
| `TOOL_CALL` | Tool được gọi + args + observation thật |
| `HALLUCINATED_OBSERVATION` | ⚠️ LLM cố tự bịa Observation — đã bị chặn |
| `TOOL_ERROR / PARSE_ERROR` | ❌ Lỗi cần phân tích |
| `AGENT_END` | Kết thúc — status, steps, total tokens |

**Parse nhanh bằng Python:**

```python
import json

with open("logs/trace_<timestamp>.jsonl", encoding="utf-8") as f:
    events = [json.loads(line) for line in f]

# Xem tất cả tool calls
tool_calls = [e for e in events if e["event"] == "TOOL_CALL"]

# Xem lỗi
errors = [e for e in events if e["event"] in ("TOOL_ERROR", "PARSE_ERROR", "HALLUCINATED_OBSERVATION")]
```

---

## 7. Kết quả đạt được

| Hạng mục | Kết quả |
|---|---|
| Chatbot Baseline | ✅ `chatbot.py` — terminal, có conversation history |
| Agent v1 (Working) | ✅ ReAct loop, 4 tools, natural language input |
| Agent v2 (Improved) | ✅ Session memory, out-of-scope guard, hallucination fix |
| Tool Design | ✅ 4 tools với mô tả rõ ràng, suggest_top_programs mới |
| Trace Quality | ✅ Per-session `.log` + `.jsonl`, 12 event types |
| Web UI | ✅ Chat interface, context pills, typing indicator |
| Pipeline Diagram | ✅ `docs/pipeline_diagram.svg` |
| Group Report | ✅ `report/group_report/GROUP_REPORT.md` |

---

*"In the world of AI, the trace is the truth."*

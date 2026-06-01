import logging
import json
import os
from datetime import datetime
from typing import Any, Dict

# Console color codes
_COLORS = {
    "AGENT_START":        "\033[1;36m",   # bold cyan
    "AGENT_STEP":         "\033[0;34m",   # blue
    "LLM_RESPONSE":       "\033[0;37m",   # white
    "THOUGHT":            "\033[0;33m",   # yellow
    "TOOL_CALL":          "\033[0;32m",   # green
    "TOOL_ERROR":         "\033[1;31m",   # bold red
    "PARSE_ERROR":        "\033[1;31m",   # bold red
    "JSON_ERROR":         "\033[1;31m",   # bold red
    "TOOL_NOT_FOUND":     "\033[1;31m",   # bold red
    "AGENT_END":          "\033[1;32m",   # bold green
    "LLM_METRIC":         "\033[0;35m",   # magenta
}
_RESET = "\033[0m"

# Events ở level ERROR để in nổi bật trên console
_ERROR_EVENTS = {"TOOL_ERROR", "PARSE_ERROR", "JSON_ERROR", "TOOL_NOT_FOUND"}


class IndustryLogger:
    """
    Structured logger — file nhận JSON thuần (dễ parse), console in màu dễ đọc.
    """

    def __init__(self, name: str = "AI-Lab-Agent", log_dir: str = "logs"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # ---- File handler: mỗi session một file riêng, JSON thuần ----
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_file = os.path.join(log_dir, f"trace_{ts}.jsonl")
        fh = logging.FileHandler(self._log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(message)s"))

        # ---- Console handler: in màu, dễ đọc khi dev ----
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(_ColorFormatter())

        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

    # ------------------------------------------------------------------

    def log_event(self, event_type: str, data: Dict[str, Any]):
        payload = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "event": event_type,
            "data": data,
        }
        raw = json.dumps(payload, ensure_ascii=False)
        if event_type in _ERROR_EVENTS:
            self.logger.error(raw)
        else:
            self.logger.info(raw)

    def info(self, msg: str):
        self.logger.info(json.dumps({"timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
                                     "event": "INFO", "data": {"msg": msg}}, ensure_ascii=False))

    def error(self, msg: str, exc_info: bool = True):
        self.logger.error(json.dumps({"timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
                                      "event": "ERROR", "data": {"msg": msg}}, ensure_ascii=False),
                          exc_info=exc_info)


class _ColorFormatter(logging.Formatter):
    """Console formatter: in màu theo event type, ẩn bớt JSON noise."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, TypeError):
            return record.getMessage()

        event = payload.get("event", "INFO")
        data  = payload.get("data", {})
        ts    = payload.get("timestamp", "")
        color = _COLORS.get(event, "\033[0m")

        # Chọn phần dữ liệu nổi bật nhất để in ra console
        if event == "AGENT_START":
            detail = f"input={data.get('input','')[:80]!r}  model={data.get('model','')}"
        elif event == "AGENT_STEP":
            detail = f"step={data.get('step')}  prompt_len={data.get('prompt_length')}"
        elif event == "LLM_RESPONSE":
            detail = f"step={data.get('step')}  response={data.get('response','')[:120]!r}"
        elif event == "THOUGHT":
            detail = f"step={data.get('step')}  >> {data.get('thought','')[:120]}"
        elif event == "TOOL_CALL":
            detail = f"step={data.get('step')}  tool={data.get('tool')}  args={data.get('args')}  obs_len={data.get('observation_length')}"
        elif event in ("TOOL_ERROR", "PARSE_ERROR", "JSON_ERROR", "TOOL_NOT_FOUND"):
            detail = f"step={data.get('step','?')}  {data}"
        elif event == "AGENT_END":
            status = data.get('status','')
            icon   = "✅" if status == "success" else "⚠️ "
            detail = f"{icon} status={status}  steps={data.get('steps')}  tokens={data.get('usage',{}).get('total_tokens','?')}"
        elif event == "LLM_METRIC":
            detail = (f"provider={data.get('provider')}  model={data.get('model')}  "
                      f"tokens={data.get('total_tokens')}  latency={data.get('latency_ms')}ms  "
                      f"cost≈${data.get('cost_estimate',0):.4f}")
        else:
            detail = str(data)[:160]

        time_str = ts[11:23]  # chỉ lấy HH:MM:SS.mmm
        return f"{color}[{time_str}] {event:<18}{_RESET}  {detail}"


# Global logger instance
logger = IndustryLogger()

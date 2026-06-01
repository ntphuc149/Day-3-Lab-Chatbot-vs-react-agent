import os
import re
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from src.core.llm_provider import LLMProvider
from src.tools.admission_tools import (
    get_subject_combination,
    search_eligible_programs,
    filter_programs_by_schools,
    suggest_top_programs,
    ADMISSION_TOOLS,
)
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker

load_dotenv()

# Chỉ 2 trường thực sự bắt buộc — truong_quan_tam là tùy chọn
_REQUIRED_FIELDS = ["diem_thi", "to_hop"]

_SCOPE_SYSTEM_PROMPT = """Xác định xem câu hỏi của người dùng có liên quan đến tuyển sinh đại học không.
Phạm vi HỢP LỆ bao gồm: điểm chuẩn, nguyện vọng, tổ hợp xét tuyển, chọn trường/ngành, cơ hội đậu đại học, học phí, thông tin tuyển sinh.
Trả lời chỉ bằng một từ: YES hoặc NO."""

_PARSE_SYSTEM_PROMPT = """Bạn là bộ trích xuất thông tin tuyển sinh. Từ câu nhập của người dùng, hãy trích xuất các trường sau dưới dạng JSON:

{
  "diem_thi": <float hoặc null>,
  "to_hop": <string mã tổ hợp như "A00","A01","B00","D01"... hoặc null>,
  "truong_quan_tam": <list string tên/mã trường, [] nếu không đề cập>,
  "nganh_quan_tam": <list string tên ngành, [] nếu không đề cập>
}

Quy tắc:
- Nếu user nói "khối A1" hoặc "A1" hãy hiểu là "A01".
- Nếu user nói "Bách Khoa" hoặc "BK" không rõ thành phố, mặc định là "Đại học Bách khoa Hà Nội".
- Tên trường viết tắt hoặc thông thường đều chấp nhận, giữ nguyên để hệ thống tự match.
- Chỉ trả về JSON, không giải thích thêm."""


class AdmissionReActAgent:
    """
    ReAct Agent tư vấn tuyển sinh đại học.
    Hỗ trợ natural language input, tự động hỏi lại khi thiếu thông tin,
    và duy trì session memory trong suốt cuộc hội thoại.
    """

    def __init__(self, llm: LLMProvider, max_steps: int = 6):
        self.llm = llm
        self.max_steps = max_steps
        self.tools = ADMISSION_TOOLS

    # ------------------------------------------------------------------
    # Public entry point — gọi từ Flask mỗi lượt chat
    # ------------------------------------------------------------------

    def chat(self, user_message: str, session: Dict[str, Any]) -> str:
        """
        Xử lý một lượt chat. `session` là dict được Flask giữ theo session_id,
        tích lũy qua nhiều lượt.

        session keys:
          - context: dict thông tin đã thu thập (diem_thi, to_hop, ...)
          - history: list các turn hội thoại để hiển thị
        """
        if "context" not in session:
            session["context"] = {}
        if "history" not in session:
            session["history"] = []

        session["history"].append({"role": "user", "content": user_message})

        # 1. Kiểm tra out-of-scope
        if not self._is_in_scope(user_message):
            reply = "Xin lỗi, tôi chỉ có thể hỗ trợ tư vấn tuyển sinh đại học (điểm chuẩn, nguyện vọng, chọn trường/ngành). Bạn có câu hỏi nào về tuyển sinh không?"
            session["history"].append({"role": "assistant", "content": reply})
            logger.log_event("OUT_OF_SCOPE", {"message": user_message})
            return reply

        # 2. Parse intent từ tin nhắn mới, merge vào context
        parsed = self._parse_user_intent(user_message)
        logger.log_event("INTENT_PARSED", {"parsed": parsed, "message": user_message})
        self._merge_context(session["context"], parsed)

        # 2. Kiểm tra thiếu thông tin
        missing = self._check_missing(session["context"])
        if missing:
            reply = self._ask_for_missing(missing, session["context"])
            session["history"].append({"role": "assistant", "content": reply})
            logger.log_event("INFO_INCOMPLETE", {"missing": missing, "context_so_far": session["context"]})
            return reply

        # 3. Đủ thông tin → chạy ReAct
        reply = self._run_react(session["context"])
        session["history"].append({"role": "assistant", "content": reply})
        return reply

    # ------------------------------------------------------------------
    # Out-of-scope check
    # ------------------------------------------------------------------

    def _is_in_scope(self, text: str) -> bool:
        result = self.llm.generate(text, system_prompt=_SCOPE_SYSTEM_PROMPT)
        answer = result["content"].strip().upper()
        return answer.startswith("YES")

    # ------------------------------------------------------------------
    # Parse natural language → structured intent
    # ------------------------------------------------------------------

    def _parse_user_intent(self, text: str) -> Dict[str, Any]:
        result = self.llm.generate(text, system_prompt=_PARSE_SYSTEM_PROMPT)
        raw = result["content"].strip()

        # Bóc JSON khỏi markdown code block nếu có
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.log_event("PARSE_ERROR", {"step": "intent_parse", "raw": raw})
            parsed = {}

        return parsed

    # ------------------------------------------------------------------
    # Merge parsed intent vào session context (không ghi đè bằng null)
    # ------------------------------------------------------------------

    def _merge_context(self, context: Dict, parsed: Dict):
        if parsed.get("diem_thi") is not None:
            context["diem_thi"] = float(parsed["diem_thi"])
        if parsed.get("to_hop"):
            context["to_hop"] = parsed["to_hop"].strip().upper()
        if parsed.get("truong_quan_tam"):
            existing = context.get("truong_quan_tam", [])
            for t in parsed["truong_quan_tam"]:
                if t not in existing:
                    existing.append(t)
            context["truong_quan_tam"] = existing
        if parsed.get("nganh_quan_tam"):
            existing = context.get("nganh_quan_tam", [])
            for n in parsed["nganh_quan_tam"]:
                if n not in existing:
                    existing.append(n)
            context["nganh_quan_tam"] = existing

    # ------------------------------------------------------------------
    # Kiểm tra thông tin còn thiếu
    # ------------------------------------------------------------------

    def _check_missing(self, context: Dict) -> List[str]:
        missing = []
        if not context.get("diem_thi"):
            missing.append("diem_thi")
        if not context.get("to_hop"):
            missing.append("to_hop")
        return missing

    def _ask_for_missing(self, missing: List[str], context: Dict) -> str:
        labels = {
            "diem_thi": "điểm thi THPT (thang 30, ví dụ: 26.5)",
            "to_hop": "tổ hợp xét tuyển (ví dụ: A00, A01, B00, D01...)",
            "truong_quan_tam": "các trường hoặc ngành bạn quan tâm (ví dụ: Bách Khoa, Ngoại Thương, Kinh tế Quốc dân...)",
        }
        missing_labels = [labels[m] for m in missing]

        # Tóm tắt những gì đã biết
        known_parts = []
        if context.get("diem_thi"):
            known_parts.append(f"điểm thi **{context['diem_thi']}**")
        if context.get("to_hop"):
            known_parts.append(f"tổ hợp **{context['to_hop']}**")
        if context.get("truong_quan_tam"):
            known_parts.append(f"trường quan tâm: **{', '.join(context['truong_quan_tam'])}**")

        known_str = ("Tôi đã ghi nhận: " + ", ".join(known_parts) + ".\n\n") if known_parts else ""

        if len(missing_labels) == 1:
            ask = f"Bạn vui lòng cho tôi biết thêm **{missing_labels[0]}** nhé?"
        else:
            items = "\n".join(f"- {l}" for l in missing_labels)
            ask = f"Bạn vui lòng cung cấp thêm các thông tin sau:\n{items}"

        return f"{known_str}{ask}"

    # ------------------------------------------------------------------
    # ReAct loop
    # ------------------------------------------------------------------

    def _run_react(self, context: Dict) -> str:
        to_hop = context["to_hop"]
        diem_thi = context["diem_thi"]
        truong_list = context.get("truong_quan_tam", [])
        nganh_list = context.get("nganh_quan_tam", [])

        if truong_list:
            nganh_str = f", ngành quan tâm: {', '.join(nganh_list)}" if nganh_list else ""
            user_input = (
                f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm (thang 30). "
                f"Các trường tôi quan tâm: {', '.join(truong_list)}{nganh_str}. "
                f"Hãy lọc các ngành phù hợp, phân tích khả năng đậu và đưa ra lời khuyên sắp xếp nguyện vọng."
            )
        else:
            nganh_str = f"Tôi có hứng thú với ngành: {', '.join(nganh_list)}. " if nganh_list else ""
            user_input = (
                f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm (thang 30). "
                f"Tôi chưa biết muốn học trường nào. {nganh_str}"
                f"Hãy dùng tool suggest_top_programs để gợi ý top 5 ngành/trường phù hợp nhất, "
                f"phân tích cơ hội và đưa ra lời khuyên."
            )

        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name, "context": context})

        conversation = user_input
        steps = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        while steps < self.max_steps:
            logger.log_event("AGENT_STEP", {"step": steps + 1, "prompt_length": len(conversation)})

            result = self.llm.generate(conversation, system_prompt=self._get_react_system_prompt())
            response_text = result["content"]

            for k in total_usage:
                total_usage[k] += result.get("usage", {}).get(k, 0)
            tracker.track_request(
                provider=result.get("provider", "openai"),
                model=self.llm.model_name,
                usage=result.get("usage", {}),
                latency_ms=result.get("latency_ms", 0),
            )

            logger.log_event("LLM_RESPONSE", {"step": steps + 1, "response": response_text})

            thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|$)", response_text, re.DOTALL)
            if thought_match:
                logger.log_event("THOUGHT", {"step": steps + 1, "thought": thought_match.group(1).strip()})

            # Cắt bỏ mọi thứ từ "Observation:" trở đi nếu LLM tự bịa
            # (chỉ giữ phần Thought + Action do LLM sinh ra)
            if "\nObservation:" in response_text:
                response_text = response_text.split("\nObservation:")[0]
                logger.log_event("HALLUCINATED_OBSERVATION", {
                    "step": steps + 1,
                    "detail": "LLM tự viết Observation — đã cắt bỏ, chỉ giữ Thought+Action",
                })

            # Final Answer chỉ hợp lệ khi KHÔNG có Action trong cùng response
            if "Final Answer:" in response_text and "Action:" not in response_text:
                final = response_text.split("Final Answer:", 1)[1].strip()
                logger.log_event("AGENT_END", {"steps": steps + 1, "usage": total_usage, "status": "success"})
                return final

            # Regex chặt hơn: chỉ lấy đến hết dòng Action, không dùng DOTALL
            action_match = re.search(r"Action:\s*(\w+)\((\{.*?\})\)", response_text, re.DOTALL)
            if not action_match:
                logger.log_event("PARSE_ERROR", {
                    "step": steps + 1,
                    "reason": "Không tìm thấy Action hợp lệ trong response",
                    "response": response_text,
                })
                conversation += f"\n{response_text}\nObservation: Không nhận được Action hợp lệ. Hãy tiếp tục hoặc đưa ra Final Answer."
                steps += 1
                continue

            tool_name = action_match.group(1).strip()
            raw_args = action_match.group(2).strip()

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as e:
                logger.log_event("JSON_ERROR", {
                    "step": steps + 1,
                    "tool": tool_name,
                    "raw_args": raw_args,
                    "error": str(e),
                })
                conversation += f"\n{response_text}\nObservation: Lỗi: tham số không phải JSON hợp lệ: {raw_args}"
                steps += 1
                continue

            observation = self._execute_tool(tool_name, args)
            logger.log_event("TOOL_CALL", {
                "step": steps + 1,
                "tool": tool_name,
                "args": args,
                "observation": observation,
                "observation_length": len(observation),
            })

            conversation += f"\n{response_text}\nObservation: {observation}"
            steps += 1

        logger.log_event("AGENT_END", {"steps": steps, "usage": total_usage, "status": "max_steps_exceeded"})
        return self._force_final_answer(conversation)

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _get_react_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in self.tools]
        )
        return f"""Bạn là một chuyên gia tư vấn tuyển sinh đại học tại Việt Nam.
Bạn có quyền truy cập các công cụ sau để tra cứu thông tin:

{tool_descriptions}

Quy tắc bắt buộc:
1. Luôn suy nghĩ trước khi hành động (Thought).
2. Gọi đúng 1 công cụ mỗi bước (Action).
3. TUYỆT ĐỐI KHÔNG tự viết "Observation:" — hệ thống sẽ điền vào sau khi chạy tool.
4. Mỗi lượt chỉ được viết Thought + Action, rồi DỪNG LẠI, chờ Observation từ hệ thống.
5. Chỉ viết Final Answer sau khi đã có Observation thật từ hệ thống.
6. KHÔNG được bịa số liệu, tên trường, điểm chuẩn — chỉ dùng dữ liệu từ Observation.

Định dạng bắt buộc:

Thought: <lý do bạn làm gì tiếp theo>
Action: <tên_tool>(<tham số JSON hợp lệ>)
Observation: <kết quả tool — hệ thống điền vào>
... (lặp lại nếu cần)
Final Answer: <câu trả lời đầy đủ, có phân tích và lời khuyên>

Ví dụ Action hợp lệ:
Action: search_eligible_programs({{"to_hop": "A00", "diem_thi": 26.5}})
Action: filter_programs_by_schools({{"to_hop": "A00", "diem_thi": 26.5, "danh_sach_truong": ["BKA", "NEU"]}})
Action: get_subject_combination({{"ma_to_hop": "A00"}})
"""

    # ------------------------------------------------------------------
    # Tool executor
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        tool_map = {
            "get_subject_combination": lambda a: get_subject_combination(a["ma_to_hop"]),
            "search_eligible_programs": lambda a: search_eligible_programs(
                to_hop=a["to_hop"],
                diem_thi=float(a["diem_thi"]),
                phuong_thuc=a.get("phuong_thuc", "THPT"),
            ),
            "filter_programs_by_schools": lambda a: filter_programs_by_schools(
                to_hop=a["to_hop"],
                diem_thi=float(a["diem_thi"]),
                danh_sach_truong=a["danh_sach_truong"],
                phuong_thuc=a.get("phuong_thuc", "THPT"),
            ),
            "suggest_top_programs": lambda a: suggest_top_programs(
                to_hop=a["to_hop"],
                diem_thi=float(a["diem_thi"]),
                top_n=int(a.get("top_n", 5)),
                nganh_quan_tam=a.get("nganh_quan_tam", []),
                phuong_thuc=a.get("phuong_thuc", "THPT"),
            ),
        }

        if tool_name not in tool_map:
            logger.log_event("TOOL_NOT_FOUND", {
                "tool_called": tool_name,
                "available_tools": list(tool_map.keys()),
            })
            return f"Lỗi: Tool '{tool_name}' không tồn tại. Tool hợp lệ: {list(tool_map.keys())}"

        try:
            return tool_map[tool_name](args)
        except KeyError as e:
            logger.log_event("TOOL_ERROR", {
                "tool": tool_name,
                "error_type": "missing_argument",
                "missing_key": str(e),
                "args_received": args,
            })
            return f"Lỗi: thiếu tham số bắt buộc {e} cho tool '{tool_name}'."
        except Exception as e:
            logger.log_event("TOOL_ERROR", {
                "tool": tool_name,
                "error_type": type(e).__name__,
                "error": str(e),
                "args_received": args,
            })
            return f"Lỗi khi thực thi tool '{tool_name}': {str(e)}"

    # ------------------------------------------------------------------
    # Fallback khi vượt max_steps
    # ------------------------------------------------------------------

    def _force_final_answer(self, conversation: str) -> str:
        prompt = conversation + "\n\nDựa trên các thông tin đã thu thập ở trên, hãy đưa ra Final Answer chi tiết ngay bây giờ."
        result = self.llm.generate(prompt, system_prompt=self._get_react_system_prompt())
        text = result["content"]
        if "Final Answer:" in text:
            return text.split("Final Answer:", 1)[1].strip()
        return text.strip()

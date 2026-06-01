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
    ADMISSION_TOOLS,
)
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker

load_dotenv()


class AdmissionReActAgent:
    """
    ReAct Agent tư vấn tuyển sinh đại học.
    Thực hiện vòng lặp Thought → Action → Observation cho đến khi có Final Answer.
    """

    def __init__(self, llm: LLMProvider, max_steps: int = 6):
        self.llm = llm
        self.max_steps = max_steps
        self.tools = ADMISSION_TOOLS

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in self.tools]
        )
        return f"""Bạn là một chuyên gia tư vấn tuyển sinh đại học tại Việt Nam.
Bạn có quyền truy cập các công cụ sau để tra cứu thông tin:

{tool_descriptions}

Quy tắc bắt buộc:
1. Luôn suy nghĩ trước khi hành động (Thought).
2. Gọi đúng 1 công cụ mỗi bước (Action).
3. Đọc kết quả công cụ (Observation) rồi tiếp tục suy nghĩ.
4. Khi đã có đủ thông tin, đưa ra Final Answer chi tiết bằng tiếng Việt.
5. KHÔNG được bịa số liệu — chỉ dùng dữ liệu từ Observation.

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
    # Main ReAct loop
    # ------------------------------------------------------------------

    def run(self, user_input: str) -> str:
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})

        # Lịch sử hội thoại tích lũy qua từng bước
        conversation = user_input
        steps = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        while steps < self.max_steps:
            logger.log_event("AGENT_STEP", {"step": steps + 1, "prompt_length": len(conversation)})

            # 1. Gọi LLM
            result = self.llm.generate(conversation, system_prompt=self.get_system_prompt())
            response_text = result["content"]

            # Ghi metrics
            for k in total_usage:
                total_usage[k] += result.get("usage", {}).get(k, 0)
            tracker.track_request(
                provider=result.get("provider", "local"),
                model=self.llm.model_name,
                usage=result.get("usage", {}),
                latency_ms=result.get("latency_ms", 0),
            )

            logger.log_event("LLM_RESPONSE", {"step": steps + 1, "response": response_text[:300]})

            # 2. Kiểm tra Final Answer
            if "Final Answer:" in response_text:
                final = response_text.split("Final Answer:", 1)[1].strip()
                logger.log_event("AGENT_END", {"steps": steps + 1, "usage": total_usage, "status": "success"})
                return final

            # 3. Parse Action
            action_match = re.search(r"Action:\s*(\w+)\((.+?)\)\s*$", response_text, re.MULTILINE | re.DOTALL)
            if not action_match:
                # LLM không ra Action — thử khai thác Thought hoặc kết thúc
                logger.log_event("PARSE_ERROR", {"step": steps + 1, "response": response_text[:200]})
                conversation += f"\n{response_text}\nObservation: Không nhận được Action hợp lệ. Hãy tiếp tục hoặc đưa ra Final Answer."
                steps += 1
                continue

            tool_name = action_match.group(1).strip()
            raw_args = action_match.group(2).strip()

            # 4. Parse arguments JSON
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                observation = f"Lỗi: tham số không phải JSON hợp lệ: {raw_args}"
                logger.log_event("TOOL_ERROR", {"tool": tool_name, "raw_args": raw_args})
                conversation += f"\n{response_text}\nObservation: {observation}"
                steps += 1
                continue

            # 5. Thực thi tool
            observation = self._execute_tool(tool_name, args)
            logger.log_event("TOOL_CALL", {"tool": tool_name, "args": args, "observation_length": len(observation)})

            # 6. Thêm vào lịch sử hội thoại
            conversation += f"\n{response_text}\nObservation: {observation}"
            steps += 1

        # Vượt max_steps
        logger.log_event("AGENT_END", {"steps": steps, "usage": total_usage, "status": "max_steps_exceeded"})
        return self._force_final_answer(conversation)

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
        }

        if tool_name not in tool_map:
            return f"Lỗi: Tool '{tool_name}' không tồn tại. Tool hợp lệ: {list(tool_map.keys())}"

        try:
            return tool_map[tool_name](args)
        except KeyError as e:
            return f"Lỗi: thiếu tham số bắt buộc {e} cho tool '{tool_name}'."
        except Exception as e:
            return f"Lỗi khi thực thi tool '{tool_name}': {str(e)}"

    # ------------------------------------------------------------------
    # Fallback khi vượt max_steps
    # ------------------------------------------------------------------

    def _force_final_answer(self, conversation: str) -> str:
        prompt = conversation + "\n\nDựa trên các thông tin đã thu thập ở trên, hãy đưa ra Final Answer chi tiết ngay bây giờ."
        result = self.llm.generate(prompt, system_prompt=self.get_system_prompt())
        text = result["content"]
        if "Final Answer:" in text:
            return text.split("Final Answer:", 1)[1].strip()
        return text.strip()
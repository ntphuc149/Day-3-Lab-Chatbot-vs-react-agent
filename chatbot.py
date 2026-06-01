"""
Chatbot Baseline — không có tools, không có ReAct loop.
Chỉ dùng LLM trả lời trực tiếp từ kiến thức có sẵn.
Mục đích: so sánh với ReAct Agent để thấy giới hạn của chatbot thuần túy.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.openai_provider import OpenAIProvider
from src.telemetry.logger import logger

SYSTEM_PROMPT = """Bạn là trợ lý tư vấn tuyển sinh đại học tại Việt Nam.
Hãy trả lời câu hỏi của người dùng dựa trên kiến thức có sẵn của bạn.
Trả lời ngắn gọn, rõ ràng bằng tiếng Việt."""

def run():
    api_key = os.getenv("OPENAI_API_KEY")
    model   = os.getenv("DEFAULT_MODEL", "gpt-4o")
    llm     = OpenAIProvider(model_name=model, api_key=api_key)

    print("=" * 55)
    print("  CHATBOT BASELINE — Tư vấn Tuyển sinh")
    print("  (không có tools, trả lời từ kiến thức LLM)")
    print("  Gõ 'exit' để thoát")
    print("=" * 55)

    history = []   # giữ context trong session

    while True:
        try:
            user_input = input("\nBạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTạm biệt!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "thoát"):
            print("Tạm biệt!")
            break

        # Gộp history vào prompt để chatbot nhớ ngữ cảnh
        history.append(f"User: {user_input}")
        conversation = "\n".join(history)

        logger.log_event("CHATBOT_INPUT", {"message": user_input})

        result  = llm.generate(conversation, system_prompt=SYSTEM_PROMPT)
        reply   = result["content"].strip()
        latency = result.get("latency_ms", 0)
        tokens  = result.get("usage", {}).get("total_tokens", "?")

        history.append(f"Assistant: {reply}")

        logger.log_event("CHATBOT_RESPONSE", {
            "response": reply,
            "latency_ms": latency,
            "total_tokens": tokens,
        })

        print(f"\nChatbot: {reply}")
        print(f"  [{latency}ms · {tokens} tokens]")


if __name__ == "__main__":
    run()

import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from src.agent.admission_agent import AdmissionReActAgent
# from src.core.local_provider import LocalProvider
from src.core.openai_provider import OpenAIProvider

load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

# ------------------------------------------------------------------
# Khởi tạo LLM provider (lazy — chỉ load khi có request đầu tiên)
# ------------------------------------------------------------------
_agent: AdmissionReActAgent = None

def get_agent() -> AdmissionReActAgent:
    global _agent
    if _agent is None:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        llm = OpenAIProvider(model_name=model, api_key=api_key)
        _agent = AdmissionReActAgent(llm=llm, max_steps=6)
    return _agent


# ------------------------------------------------------------------
# Helper: đọc danh sách trường từ diem_chuan.json
# ------------------------------------------------------------------
def _load_schools():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "diem_chuan.json")
    with open(data_path, encoding="utf-8") as f:
        records = json.load(f)
    seen = {}
    for r in records:
        ma = r["ma_truong"]
        if ma not in seen and r.get("phuong_thuc") == "THPT":
            seen[ma] = r["ten_truong"]
    return [{"ma": k, "ten": v} for k, v in sorted(seen.items(), key=lambda x: x[1])]


def _load_to_hop():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "to_hop_mon.json")
    with open(data_path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/schools", methods=["GET"])
def get_schools():
    return jsonify(_load_schools())


@app.route("/api/to_hop", methods=["GET"])
def get_to_hop():
    return jsonify(_load_to_hop())


@app.route("/api/advise", methods=["POST"])
def advise():
    body = request.get_json()
    if not body:
        return jsonify({"error": "Request body trống"}), 400

    to_hop: str = body.get("to_hop", "").strip().upper()
    diem_thi = body.get("diem_thi")
    danh_sach_truong: list = body.get("danh_sach_truong", [])

    if not to_hop:
        return jsonify({"error": "Thiếu tổ hợp xét tuyển"}), 400
    if diem_thi is None:
        return jsonify({"error": "Thiếu điểm thi"}), 400
    try:
        diem_thi = float(diem_thi)
    except (ValueError, TypeError):
        return jsonify({"error": "Điểm thi không hợp lệ"}), 400
    if not (0 <= diem_thi <= 30):
        return jsonify({"error": "Điểm thi phải trong khoảng 0–30"}), 400

    # Xây dựng câu hỏi cho agent
    if danh_sach_truong:
        ten_truong_list = ", ".join(danh_sach_truong)
        user_query = (
            f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm (thang 30). "
            f"Tôi quan tâm đến các trường sau: {ten_truong_list}. "
            f"Hãy lọc các ngành phù hợp tại các trường đó, phân tích khả năng đậu và đưa ra lời khuyên sắp xếp nguyện vọng."
        )
    else:
        user_query = (
            f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm (thang 30). "
            f"Hãy tìm tất cả ngành/trường phù hợp với điểm của tôi, "
            f"phân tích và đưa ra lời khuyên sắp xếp nguyện vọng hợp lý."
        )

    try:
        agent = get_agent()
        answer = agent.run(user_query)
        return jsonify({"answer": answer, "query": user_query})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)